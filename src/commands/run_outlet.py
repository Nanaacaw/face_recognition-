from __future__ import annotations

import multiprocessing
import time
import os
import json
import sys
import queue
import cv2

from src.pipeline.inference_server import InferenceServer
from src.pipeline.shared_frame_buffer import SharedFrameBuffer
from src.pipeline.outlet_aggregator import OutletAggregator
from src.domain.events import Event
from src.notification.telegram_notifier import TelegramNotifier
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.rtsp_reader import RTSPReader
from src.storage.event_store import EventStore
from src.storage.snapshot_store import SnapshotStore
from src.settings.settings import load_settings
from dotenv import load_dotenv

from src.settings.logger import logger
from src.storage.snapshot_cleaner import SnapshotCleaner


# --- LIGHTWEIGHT CAMERA WORKER ---
def worker_camera_capture(
    camera_id: str, 
    source_url: str, 
    process_fps: int,
    loop_video: bool,
    input_queue: multiprocessing.Queue,
    feedback_queue: multiprocessing.Queue,
    data_dir: str,
    outlet_id: str,
    shm_name: str | None = None,
    shm_max_h: int = 720,
    shm_max_w: int = 1280,
    shm_lock: multiprocessing.Lock | None = None,
):
    """
    Lightweight camera capture process:
    1. Reads frame from RTSP/Webcam/File
    2. Writes frame to Shared Memory (zero-copy) or Queue (fallback)
    3. Sends lightweight metadata to input_queue
    4. Reads inference results from feedback_queue -> Draws visualization
    5. Saves preview thumbnail for dashboard
    """
    logger.info(f"[CamWorker {camera_id}] Starting capture process...")
    
    os.makedirs(data_dir, exist_ok=True)
    
    # Setup Reader
    if source_url == "webcam" or (isinstance(source_url, str) and source_url.isdigit()):
        idx = int(source_url) if source_url.isdigit() else 0
        reader = WebcamReader(idx, process_fps)
    else:
        reader = RTSPReader(source_url, process_fps)
        reader.set_loop(loop_video)
        
    reader.start()
    
    # Attach to Shared Memory (if available)
    shm_buf = None
    if shm_name:
        try:
            shm_buf = SharedFrameBuffer.attach(shm_name, shm_max_h, shm_max_w, shm_lock)
            logger.info(f"[CamWorker {camera_id}] Using shared memory.")
        except Exception as e:
            logger.warning(f"[CamWorker {camera_id}] Shared memory failed, falling back to queue: {e}")
    
    frame_id = 0
    last_frame_time = 0
    preview_path = os.path.join(data_dir, "snapshots", "latest_frame.jpg")
    os.makedirs(os.path.dirname(preview_path), exist_ok=True)

    # State for drawing inference results
    latest_faces = []

    try:
        while True:
            # A. Read Frame
            frame = reader.read_throttled()
            now = time.time()
            
            # B. Check for New Inference Results (Non-blocking drain)
            try:
                while True:
                    res = feedback_queue.get_nowait()
                    if res['camera_id'] == camera_id:
                        latest_faces = res['faces']
            except (queue.Empty, AttributeError):
                pass
            
            if frame is not None:
                frame_id += 1
                
                # C. Send to Inference
                try:
                    if shm_buf:
                        # Shared Memory Mode: resize if needed, then write
                        inf_frame = frame
                        h, w = inf_frame.shape[:2]
                        bbox_scale = 1.0
                        if h > shm_max_h or w > shm_max_w:
                            bbox_scale = min(shm_max_h / h, shm_max_w / w)
                            inf_frame = cv2.resize(inf_frame, (int(w * bbox_scale), int(h * bbox_scale)))
                        shm_buf.write(inf_frame, frame_id, now)
                        input_queue.put((camera_id, frame_id, now), timeout=0.1)
                    else:
                        # Queue Mode (fallback): send frame via queue
                        bbox_scale = 1.0
                        input_queue.put((camera_id, frame_id, frame, now), timeout=0.1)
                except queue.Full:
                    pass  # Backpressure: drop frame
                except Exception:
                    pass

                # D. Draw Visualization (async, 1-2 frames behind is acceptable)
                # Bbox coords are from the resized frame, scale back to original
                inv_scale = 1.0 / bbox_scale if bbox_scale > 0 else 1.0
                for f in latest_faces:
                    bbox = f['bbox']
                    x1 = int(bbox[0] * inv_scale)
                    y1 = int(bbox[1] * inv_scale)
                    x2 = int(bbox[2] * inv_scale)
                    y2 = int(bbox[3] * inv_scale)
                    
                    color = (0, 255, 0) if f['matched'] else (0, 0, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    label = f"{f['name']} ({f['similarity']:.2f})"
                    cv2.putText(frame, label, (x1, max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                # E. Save preview thumbnail (5x per second)
                if now - last_frame_time > 0.2:
                    try:
                        h, w = frame.shape[:2]
                        # Resize for dashboard (width 640)
                        small = cv2.resize(frame, (640, int(h * 640 / w)))
                        cv2.imwrite(preview_path, small, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        last_frame_time = now
                    except: pass

            else:
                 time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"[CamWorker {camera_id}] Error: {e}")
    finally:
        if shm_buf:
            shm_buf.close()
        reader.stop()
        logger.info(f"[CamWorker {camera_id}] Stopped.")


def run_outlet(preview: bool = False, force_simulate: bool = False):
    """
    Main Runner: Centralized Inference (Sidecar Pattern)
    
    Architecture:
      Camera Workers → SharedMemory + metadata Queue → InferenceServer (1 model)
                                                              ↓
      Main Process ← output_queue ← InferenceServer
        ├→ feedback_queues[cam_id] → Workers (visualization)
        └→ OutletAggregator → Events → Alerts
    """
    settings = load_settings()
    
    if settings.outlet is None:
        logger.error("No 'outlet' section found.")
        sys.exit(1)
        
    outlet = settings.outlet
    outlet_id = outlet.id
    target_spg_ids = outlet.target_spg_ids
    
    logger.info(f"=== Outlet Started: {outlet_id} (Centralized Mode) ===")
    
    use_simulation = force_simulate or settings.dev.simulate
    camera_sources = [] 
    loop_video = False
    
    if use_simulation and settings.dev.video_files:
        logger.info(f"[Mode] SIMULATION — using {len(settings.dev.video_files)} video file(s)")
        loop_video = True
        for i, vf in enumerate(settings.dev.video_files):
            if not os.path.exists(vf): continue
            camera_sources.append((f"cam_{i+1:02d}", vf))
    else:
        logger.info(f"[Mode] PRODUCTION — using {len(outlet.cameras)} RTSP camera(s)")
        for cam in outlet.cameras:
            camera_sources.append((cam.id, cam.rtsp_url))
            
    if not camera_sources:
        logger.error("No valid cameras.")
        sys.exit(1)

    # Directories
    base_data_dir = os.path.join(settings.storage.data_dir, "sim_output")
    os.makedirs(base_data_dir, exist_ok=True)
    
    old_state = os.path.join(base_data_dir, "outlet_state.json")
    if os.path.exists(old_state): os.remove(old_state)
    
    try:
        SnapshotCleaner(settings.storage.data_dir, 3).clean()
    except: pass

    # IPC
    input_queue = multiprocessing.Queue(maxsize=10) 
    output_queue = multiprocessing.Queue()
    
    # Feedback Queues (Main → Worker, for visualization)
    worker_feedback_queues = {}
    for cam_id, _ in camera_sources:
        worker_feedback_queues[cam_id] = multiprocessing.Queue(maxsize=5)

    # Shared Memory Buffers (per camera)
    max_h = settings.inference.max_frame_height
    max_w = settings.inference.max_frame_width
    frame_skip = settings.inference.frame_skip
    
    shared_buffers = {}
    shared_locks = {}
    shared_buffer_configs = {}
    
    for cam_id, _ in camera_sources:
        lock = multiprocessing.Lock()
        try:
            buf = SharedFrameBuffer.create(cam_id, max_h, max_w, lock)
            shared_buffers[cam_id] = buf
            shared_locks[cam_id] = lock
            shared_buffer_configs[cam_id] = (cam_id, max_h, max_w, lock)
        except Exception as e:
            logger.warning(f"[SharedMem] Failed to create buffer for {cam_id}: {e}. Using queue fallback.")

    use_shm = len(shared_buffers) == len(camera_sources)
    if use_shm:
        logger.info(f"[SharedMem] Created {len(shared_buffers)} buffers ({max_h}x{max_w})")
    else:
        # Cleanup partial buffers
        for buf in shared_buffers.values():
            buf.close()
            buf.unlink()
        shared_buffers.clear()
        shared_buffer_configs.clear()
        logger.info("[SharedMem] Disabled, using queue mode.")

    logger.info(f"[Config] frame_skip={frame_skip}")

    # Start Inference Server
    server = InferenceServer(
        input_queue=input_queue,
        output_queue=output_queue,
        model_name=settings.recognition.model_name,
        execution_providers=settings.recognition.execution_providers,
        det_size=tuple(settings.recognition.det_size),
        threshold=settings.recognition.threshold,
        gallery_path=settings.storage.data_dir,
        shared_buffers=shared_buffer_configs if use_shm else None,
        frame_skip=frame_skip,
    )
    
    p_server = multiprocessing.Process(target=server.run)
    p_server.daemon = True
    p_server.start()
    
    # Start Camera Workers
    processes = [p_server]
    cam_dirs = {}
    
    for cam_id, src in camera_sources:
        d = os.path.join(base_data_dir, cam_id)
        cam_dirs[cam_id] = d
        
        worker_kwargs = dict(
            camera_id=cam_id,
            source_url=src,
            process_fps=settings.camera.process_fps,
            loop_video=loop_video,
            input_queue=input_queue,
            feedback_queue=worker_feedback_queues[cam_id],
            data_dir=d,
            outlet_id=outlet_id,
        )
        
        if use_shm:
            worker_kwargs.update(
                shm_name=cam_id,
                shm_max_h=max_h,
                shm_max_w=max_w,
                shm_lock=shared_locks[cam_id],
            )
        
        p = multiprocessing.Process(target=worker_camera_capture, kwargs=worker_kwargs)
        p.daemon = True
        p.start()
        processes.append(p)
        logger.info(f"[Started] {cam_id} -> {src}")

    # Aggregator
    aggregator = OutletAggregator(
        outlet_id, 
        absent_seconds=settings.presence.absent_seconds,
        target_spg_ids=target_spg_ids
    )
    
    event_stores = {cid: EventStore(d) for cid, d in cam_dirs.items()}
    
    # Telegram
    load_dotenv()
    notifier = None
    if settings.notification.telegram_enabled:
        try:
            notifier = TelegramNotifier.from_env()
        except Exception as e:
            logger.warning(f"Telegram notifier disabled: {e}")
    else:
        logger.info("Telegram notification disabled in config.")
    
    logger.info("[Main] Centralized Loop active.")
    state_path = os.path.join(base_data_dir, "outlet_state.json")
    
    try:
        while True:
            # Drain output queue
            events_batch = []
            for _ in range(50):
                try:
                    res = output_queue.get_nowait()
                    cid = res['camera_id']
                    
                    # 1. Dispatch copy to Worker for Visualization
                    if cid in worker_feedback_queues:
                        try:
                            worker_feedback_queues[cid].put_nowait(res)
                        except queue.Full:
                            pass  # Viz lag is fine

                    # 2. Process Events
                    for f in res['faces']:
                        if f['matched'] and f['spg_id'] in target_spg_ids:
                            ev = Event(
                                event_type="SPG_SEEN",
                                outlet_id=outlet_id,
                                camera_id=cid,
                                spg_id=f['spg_id'],
                                name=f['name'],
                                similarity=f['similarity'],
                                ts=res['timestamp'],
                                details={"frame_id": res['frame_id']}
                            )
                            if cid in event_stores:
                                event_stores[cid].append(ev)
                            events_batch.append(ev)

                except queue.Empty:
                    break

            if events_batch:
                aggregator.ingest_events(events_batch)
            
            alerts = aggregator.tick()
            
            for al in alerts:
                reason = al.details.get("reason", "unknown")
                spg = al.name or al.spg_id
                logger.info(f"[Alert] Sending Telegram: ABSENCE {spg} ({reason})")
                if notifier:
                    try: notifier.send_message(txt)
                    except: pass
            
            aggregator.dump_state(state_path)
            
            if not p_server.is_alive():
                logger.error("Inference Died")
                break
                
            time.sleep(0.05)

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        for p in processes: p.terminate()
        # Cleanup shared memory
        for buf in shared_buffers.values():
            buf.close()
            buf.unlink()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()
    
    run_outlet(preview=(args.preview and not args.no_preview), force_simulate=args.simulate)
