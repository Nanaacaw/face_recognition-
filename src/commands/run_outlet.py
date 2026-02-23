from __future__ import annotations

import multiprocessing
import time
import os
import sys
import queue
import json
from collections import deque
import cv2

from src.pipeline.inference_server import InferenceServer
from src.pipeline.shared_frame_buffer import SharedFrameBuffer
from src.pipeline.outlet_aggregator import OutletAggregator
from src.domain.events import Event
from src.notification.telegram_notifier import TelegramNotifier
from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.rtsp_reader import RTSPReader
from src.storage.event_store import EventStore
from src.settings.settings import load_settings

from src.settings.logger import logger
from src.storage.snapshot_cleaner import SnapshotCleaner


def _safe_write_json(filepath: str, payload: dict, retries: int = 3, retry_sleep_sec: float = 0.05) -> None:
    """Best-effort JSON write with simple retry to handle transient file locks."""
    for attempt in range(retries):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(retry_sleep_sec)
        except OSError as e:
            logger.warning(f"[Main] Failed writing {filepath}: {e}")
            return


def _source_type(source_url: str) -> str:
    src = str(source_url).lower()
    if src == "webcam" or src.isdigit():
        return "webcam"
    if src.startswith("rtsp://"):
        return "rtsp"
    return "file"


# LIGHTWEIGHT CAMERA WORKER
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
    preview_frame_save_interval_sec: float = 0.2,
    preview_frame_width: int = 640,
    preview_jpeg_quality: int = 80,
    save_raw_preview: bool = True,
    idle_sleep_sec: float = 0.05,
    preview: bool = False,
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
    raw_preview_path = os.path.join(data_dir, "snapshots", "latest_raw_frame.jpg")
    os.makedirs(os.path.dirname(preview_path), exist_ok=True)

    latest_faces = []

    try:
        while True:
            frame = reader.read_throttled()
            now = time.time()
            
            try:
                while True:
                    res = feedback_queue.get_nowait()
                    if res['camera_id'] == camera_id:
                        latest_faces = res['faces']
            except (queue.Empty, AttributeError):
                pass
            
            if frame is not None:
                frame_id += 1
                raw_frame = frame.copy() if save_raw_preview else None
                
                try:
                    if shm_buf:
                        inf_frame = frame
                        h, w = inf_frame.shape[:2]
                        bbox_scale = 1.0
                        if h > shm_max_h or w > shm_max_w:
                            bbox_scale = min(shm_max_h / h, shm_max_w / w)
                            inf_frame = cv2.resize(inf_frame, (int(w * bbox_scale), int(h * bbox_scale)))
                        shm_buf.write(inf_frame, frame_id, now)
                        input_queue.put((camera_id, frame_id, now), timeout=0.1)
                    else:
                        bbox_scale = 1.0
                        input_queue.put((camera_id, frame_id, frame, now), timeout=0.1)
                except queue.Full:
                    pass
                except Exception:
                    pass

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

                if now - last_frame_time > preview_frame_save_interval_sec:
                    try:
                        h, w = frame.shape[:2]
                        if w > 0:
                            if save_raw_preview and raw_frame is not None:
                                raw_small = cv2.resize(raw_frame, (preview_frame_width, int(h * preview_frame_width / w)))
                                cv2.imwrite(raw_preview_path, raw_small, [cv2.IMWRITE_JPEG_QUALITY, preview_jpeg_quality])

                            ai_small = cv2.resize(frame, (preview_frame_width, int(h * preview_frame_width / w)))
                            cv2.imwrite(preview_path, ai_small, [cv2.IMWRITE_JPEG_QUALITY, preview_jpeg_quality])
                            last_frame_time = now
                    except Exception:
                        pass

                if preview:
                    cv2.imshow(f"face_recog | {camera_id}", frame)
                    cv2.waitKey(1)

            else:
                time.sleep(idle_sleep_sec)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"[CamWorker {camera_id}] Error: {e}")
    finally:
        if shm_buf:
            shm_buf.close()
        reader.stop()
        if preview:
            cv2.destroyAllWindows()
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
    base_data_dir = os.path.join(settings.storage.data_dir, settings.storage.sim_output_subdir)
    os.makedirs(base_data_dir, exist_ok=True)
    
    old_state = os.path.join(base_data_dir, "outlet_state.json")
    if os.path.exists(old_state): os.remove(old_state)
    
    try:
        SnapshotCleaner(settings.storage.data_dir, settings.storage.snapshot_retention_days).clean()
    except Exception:
        pass

    # IPC
    input_queue = multiprocessing.Queue(maxsize=10) 
    output_queue = multiprocessing.Queue()
    
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
            preview_frame_save_interval_sec=settings.runtime.preview_frame_save_interval_sec,
            preview_frame_width=settings.runtime.preview_frame_width,
            preview_jpeg_quality=settings.runtime.preview_jpeg_quality,
            save_raw_preview=settings.runtime.preview_raw_enabled,
            idle_sleep_sec=settings.runtime.worker_idle_sleep_sec,
            preview=preview,
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
    source_by_camera = {cam_id: src for cam_id, src in camera_sources}
    camera_metrics = {
        cam_id: {
            "source_type": _source_type(src),
            "last_result_ts": 0.0,
            "last_frame_id": 0,
            "processed_frames": 0,
            "events_count": 0,
            "last_event_ts": 0.0,
            "inference_time_ema_ms": None,
            "queue_lag_ema_ms": None,
        }
        for cam_id, src in camera_sources
    }
    result_windows = {cam_id: deque(maxlen=120) for cam_id, _ in camera_sources}
    
    # Telegram
    notifier = None
    if settings.notification.telegram_enabled:
        try:
            notifier = TelegramNotifier.from_env(
                token_env=settings.notification.telegram_bot_token_env,
                chat_id_env=settings.notification.telegram_chat_id_env,
                timeout_sec=settings.notification.timeout_sec,
                max_retries=settings.notification.max_retries,
                retry_backoff_base_sec=settings.notification.retry_backoff_base_sec,
                retry_after_default_sec=settings.notification.retry_after_default_sec,
            )
        except Exception as e:
            logger.warning(f"Telegram notifier disabled: {e}")
    else:
        logger.info("Telegram notification disabled in config.")
    
    logger.info("[Main] Centralized Loop active.")
    state_path = os.path.join(base_data_dir, "outlet_state.json")
    health_path = os.path.join(base_data_dir, "camera_health.json")
    
    try:
        while True:
            # Drain output queue
            events_batch = []
            for _ in range(50):
                try:
                    res = output_queue.get_nowait()
                    cid = res['camera_id']
                    now_ts = time.time()

                    metrics = camera_metrics.get(cid)
                    if metrics is not None:
                        metrics["processed_frames"] += 1
                        result_ts = float(res.get("timestamp", now_ts))
                        metrics["last_result_ts"] = result_ts
                        metrics["last_frame_id"] = int(res.get("frame_id", 0))
                        result_windows[cid].append(now_ts)

                        inf_ms = float(res.get("inference_time_ms", 0.0))
                        prev_inf = metrics["inference_time_ema_ms"]
                        metrics["inference_time_ema_ms"] = inf_ms if prev_inf is None else (0.2 * inf_ms + 0.8 * prev_inf)

                        lag_ms = max(0.0, (now_ts - result_ts) * 1000.0)
                        prev_lag = metrics["queue_lag_ema_ms"]
                        metrics["queue_lag_ema_ms"] = lag_ms if prev_lag is None else (0.2 * lag_ms + 0.8 * prev_lag)
                    
                    if cid in worker_feedback_queues:
                        try:
                            worker_feedback_queues[cid].put_nowait(res)
                        except queue.Full:
                            pass

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
                            if metrics is not None:
                                metrics["events_count"] += 1
                                metrics["last_event_ts"] = float(res.get("timestamp", now_ts))

                except queue.Empty:
                    break

            if events_batch:
                aggregator.ingest_events(events_batch)
            
            alerts = aggregator.tick()
            
            for al in alerts:
                reason = al.details.get("reason", "unknown")
                spg = al.name or al.spg_id
                ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(al.ts))
                txt = (
                    "SPG ABSENCE DETECTED\n"
                    f"Outlet: {al.outlet_id}\n"
                    f"SPG: {spg} ({al.spg_id})\n"
                    f"Reason: {reason}\n"
                    f"Time: {ts_str}"
                )
                logger.info(f"[Alert] Sending Telegram: ABSENCE {spg} ({reason})")
                if notifier:
                    try:
                        notifier.send_message(txt)
                    except Exception:
                        pass

            health_now = time.time()
            health_payload = {
                "timestamp": health_now,
                "outlet_id": outlet_id,
                "cameras": [],
            }
            for cam_id, src in source_by_camera.items():
                m = camera_metrics.get(cam_id, {})
                window = result_windows.get(cam_id, deque())
                processed_fps = 0.0
                if len(window) >= 2:
                    duration = window[-1] - window[0]
                    if duration > 0:
                        processed_fps = (len(window) - 1) / duration

                last_result_ts = float(m.get("last_result_ts") or 0.0)
                result_age_sec = None if last_result_ts <= 0 else max(0.0, health_now - last_result_ts)

                if result_age_sec is None or result_age_sec > 10.0:
                    status = "OFFLINE"
                elif result_age_sec > 2.0:
                    status = "STALE"
                else:
                    status = "LIVE"

                health_payload["cameras"].append(
                    {
                        "camera_id": cam_id,
                        "source_type": m.get("source_type", _source_type(src)),
                        "status": status,
                        "processed_fps": round(processed_fps, 2),
                        "inference_time_ms": round(float(m.get("inference_time_ema_ms") or 0.0), 1),
                        "queue_lag_ms": round(float(m.get("queue_lag_ema_ms") or 0.0), 1),
                        "last_result_age_sec": None if result_age_sec is None else round(result_age_sec, 2),
                        "last_frame_id": int(m.get("last_frame_id") or 0),
                        "events_count": int(m.get("events_count") or 0),
                    }
                )
            _safe_write_json(health_path, health_payload)
            
            aggregator.dump_state(state_path)
            
            if not p_server.is_alive():
                logger.error("Inference Died")
                break
                
            time.sleep(settings.runtime.main_loop_sleep_sec)

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        for p in processes: p.terminate()
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
