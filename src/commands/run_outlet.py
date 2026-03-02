from __future__ import annotations

import multiprocessing
import time
import os
import sys
import queue
import json
import re
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

from src.storage.snapshot_store import SnapshotStore

_UNRESOLVED_ENV_PATTERN = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}|%[A-Za-z_][A-Za-z0-9_]*%")


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


def _write_jpeg_atomic(
    filepath: str,
    frame,
    jpeg_quality: int,
    retries: int = 2,
    retry_sleep_sec: float = 0.01,
) -> bool:
    """
    Encode to JPEG in-memory and atomically replace destination file.
    This prevents readers from seeing partially-written JPEG bytes.
    """
    try:
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)],
        )
        if not ok:
            return False
        payload = encoded.tobytes()
    except Exception:
        return False

    tmp_path = f"{filepath}.tmp"
    for attempt in range(retries):
        try:
            with open(tmp_path, "wb") as f:
                f.write(payload)
            os.replace(tmp_path, filepath)
            return True
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(retry_sleep_sec)
        except OSError:
            if attempt < retries - 1:
                time.sleep(retry_sleep_sec)

    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except OSError:
        pass
    return False


def _source_type(source_url: str) -> str:
    src = str(source_url).lower()
    if src == "webcam" or src.isdigit():
        return "webcam"
    if src.startswith("rtsp://"):
        return "rtsp"
    return "file"


def _has_unresolved_env_placeholder(value: str | None) -> bool:
    if not value:
        return False
    return bool(_UNRESOLVED_ENV_PATTERN.search(str(value)))


def _restart_allowed(restart_history: deque[float], max_restarts_per_minute: int) -> bool:
    """Sliding-window restart budget guard (60s)."""
    now = time.time()
    while restart_history and (now - restart_history[0]) > 60.0:
        restart_history.popleft()
    if len(restart_history) >= max_restarts_per_minute:
        return False
    restart_history.append(now)
    return True


def _terminate_process(proc: multiprocessing.Process | None, name: str = "process", timeout_sec: float = 1.0) -> None:
    if proc is None:
        return
    try:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=timeout_sec)
    except Exception as e:
        logger.warning(f"[Supervisor] Failed terminating {name}: {e}")


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
                capture_ts = now
                 
                try:
                    if shm_buf:
                        inf_frame = frame
                        h, w = inf_frame.shape[:2]
                        bbox_scale = 1.0
                        
                        if h > shm_max_h or w > shm_max_w:
                            bbox_scale = min(shm_max_h / h, shm_max_w / w)
                            inf_frame = cv2.resize(inf_frame, (int(w * bbox_scale), int(h * bbox_scale)))
                         
                        shm_buf.write(inf_frame, frame_id, now)
                        enqueue_ts = time.time()
                        input_queue.put((camera_id, frame_id, capture_ts, enqueue_ts), timeout=0.1)
                    else:
                        inf_frame = frame
                        h, w = inf_frame.shape[:2]
                        bbox_scale = 1.0
                        # Hard limit for Queue mode to avoid OOM/Slow pickle
                        QUEUE_MAX_W = 1280
                        QUEUE_MAX_H = 720
                        if h > QUEUE_MAX_H or w > QUEUE_MAX_W:
                            bbox_scale = min(QUEUE_MAX_H / h, QUEUE_MAX_W / w)
                            inf_frame = cv2.resize(inf_frame, (int(w * bbox_scale), int(h * bbox_scale)))
                             
                        enqueue_ts = time.time()
                        input_queue.put((camera_id, frame_id, inf_frame, capture_ts, enqueue_ts), timeout=0.1)
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
                        if w > 0 and preview_frame_width > 0:
                            target_h = max(1, int(h * preview_frame_width / w))
                            if save_raw_preview and raw_frame is not None:
                                raw_small = cv2.resize(raw_frame, (preview_frame_width, target_h))
                                _write_jpeg_atomic(raw_preview_path, raw_small, preview_jpeg_quality)

                            ai_small = cv2.resize(frame, (preview_frame_width, target_h))
                            if _write_jpeg_atomic(preview_path, ai_small, preview_jpeg_quality):
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


def run_outlet(
    preview: bool = False,
    force_simulate: bool = False,
    config_path: str | None = None,
):
    """
    Main Runner: Centralized Inference (Sidecar Pattern)
    
    Architecture:
      Camera Workers → SharedMemory + metadata Queue → InferenceServer (1 model)
                                                              ↓
      Main Process ← output_queue ← InferenceServer
        ├→ feedback_queues[cam_id] → Workers (visualization)
        └→ OutletAggregator → Events → Alerts
    """
    settings = load_settings(config_path)
    
    if settings.outlet is None:
        logger.error("No 'outlet' section found.")
        sys.exit(1)
        
    outlet = settings.outlet
    outlet_id = outlet.id
    target_spg_ids = outlet.target_spg_ids
    target_spg_set = set(target_spg_ids)
    min_hits_base = max(1, int(settings.recognition.min_consecutive_hits))
    configured_roi_by_camera = {cam.id: cam.roi for cam in outlet.cameras}
    
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
            
    if not use_simulation:
        unresolved = [cam_id for cam_id, src in camera_sources if _has_unresolved_env_placeholder(src)]
        if unresolved:
            logger.error(
                "Missing RTSP env vars for: %s. Set RTSP_CAM_XX_URL in .env.",
                ", ".join(unresolved),
            )
            sys.exit(1)

    if not camera_sources:
        logger.error("No valid cameras.")
        sys.exit(1)

    roi_by_camera = {cam_id: configured_roi_by_camera.get(cam_id) for cam_id, _ in camera_sources}
    roi_enabled_cameras = [cam_id for cam_id, roi in roi_by_camera.items() if roi is not None]

    # Directories
    base_data_dir = os.path.join(settings.storage.data_dir, settings.storage.sim_output_subdir)
    os.makedirs(base_data_dir, exist_ok=True)
    
    old_state = os.path.join(base_data_dir, "outlet_state.json")
    if os.path.exists(old_state): os.remove(old_state)
    
    try:
        SnapshotCleaner(
            settings.storage.data_dir,
            settings.storage.snapshot_retention_days,
            sim_output_subdir=settings.storage.sim_output_subdir,
        ).clean()
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
    frame_skip_base = max(0, int(settings.inference.frame_skip))
    frame_skip_control = multiprocessing.Value("i", frame_skip_base)
    min_det_score_base = max(0.0, float(settings.recognition.min_det_score))
    min_det_score_control = multiprocessing.Value("d", min_det_score_base)
    min_face_width_base = max(0, int(settings.recognition.min_face_width_px))
    min_face_width_control = multiprocessing.Value("i", min_face_width_base)
    min_hits_control = multiprocessing.Value("i", min_hits_base)
    
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

    # Runtime control file (optional hot-tuning from dashboard)
    control_path = os.path.join(base_data_dir, "runtime_control.json")
    control_last_mtime = 0.0

    logger.info(f"[Config] base_frame_skip={frame_skip_base}")
    logger.info(
        "[Config] min_consecutive_hits=%s, min_det_score=%.2f, min_face_width_px=%s",
        min_hits_base,
        min_det_score_base,
        min_face_width_base,
    )
    logger.info(
        "[Config] ROI cameras: %s",
        ", ".join(roi_enabled_cameras) if roi_enabled_cameras else "none (full frame)",
    )
    logger.info("[Config] runtime_control_file=%s", control_path)

    # Supervisor and adaptive runtime controls
    restart_cooldown_sec = max(0.5, float(settings.runtime.supervisor_restart_cooldown_sec))
    max_restarts_per_minute = max(1, int(settings.runtime.supervisor_max_restarts_per_minute))
    auto_degrade_enabled = bool(settings.runtime.auto_degrade_enabled)
    auto_degrade_lag_high_ms = max(1.0, float(settings.runtime.auto_degrade_lag_high_ms))
    auto_degrade_lag_low_ms = max(0.0, float(settings.runtime.auto_degrade_lag_low_ms))
    auto_degrade_high_streak_target = max(1, int(settings.runtime.auto_degrade_high_streak))
    auto_degrade_low_streak_target = max(1, int(settings.runtime.auto_degrade_low_streak))
    auto_degrade_max_skip = max(frame_skip_base, int(settings.runtime.auto_degrade_max_frame_skip))

    if auto_degrade_lag_low_ms >= auto_degrade_lag_high_ms:
        auto_degrade_lag_low_ms = max(0.0, auto_degrade_lag_high_ms * 0.6)

    def _apply_runtime_control() -> None:
        nonlocal control_last_mtime
        nonlocal auto_degrade_enabled

        if not os.path.exists(control_path):
            return
        try:
            mtime = os.path.getmtime(control_path)
        except OSError:
            return
        if mtime <= control_last_mtime:
            return

        try:
            with open(control_path, "r", encoding="utf-8") as f:
                payload = json.load(f) or {}
        except Exception as e:
            logger.warning(f"[RuntimeControl] Failed reading control file: {e}")
            control_last_mtime = mtime
            return

        if not isinstance(payload, dict):
            control_last_mtime = mtime
            return

        changed = []
        if "frame_skip" in payload:
            try:
                frame_skip_control.value = max(0, int(payload["frame_skip"]))
                changed.append(f"frame_skip={int(frame_skip_control.value)}")
            except Exception:
                pass
        if "min_consecutive_hits" in payload:
            try:
                min_hits_control.value = max(1, int(payload["min_consecutive_hits"]))
                changed.append(f"min_consecutive_hits={int(min_hits_control.value)}")
            except Exception:
                pass
        if "min_det_score" in payload:
            try:
                min_det_score_control.value = max(0.0, float(payload["min_det_score"]))
                changed.append(f"min_det_score={float(min_det_score_control.value):.2f}")
            except Exception:
                pass
        if "min_face_width_px" in payload:
            try:
                min_face_width_control.value = max(0, int(payload["min_face_width_px"]))
                changed.append(f"min_face_width_px={int(min_face_width_control.value)}")
            except Exception:
                pass
        if "auto_degrade_enabled" in payload:
            try:
                auto_degrade_enabled = bool(payload["auto_degrade_enabled"])
                changed.append(f"auto_degrade_enabled={auto_degrade_enabled}")
            except Exception:
                pass

        control_last_mtime = mtime
        if changed:
            logger.info("[RuntimeControl] Applied: %s", ", ".join(changed))

    # Start / restart helpers
    def _spawn_inference() -> multiprocessing.Process:
        server = InferenceServer(
            input_queue=input_queue,
            output_queue=output_queue,
            model_name=settings.recognition.model_name,
            execution_providers=settings.recognition.execution_providers,
            det_size=tuple(settings.recognition.det_size),
            threshold=settings.recognition.threshold,
            gallery_path=settings.storage.data_dir,
            gallery_subdir=settings.storage.gallery_subdir,
            shared_buffers=shared_buffer_configs if use_shm else None,
            frame_skip=frame_skip_base,
            frame_skip_value=frame_skip_control,
            min_det_score=min_det_score_base,
            min_face_width_px=min_face_width_base,
            min_det_score_value=min_det_score_control,
            min_face_width_px_value=min_face_width_control,
            roi_by_camera=roi_by_camera,
        )
        proc = multiprocessing.Process(target=server.run, name="inference_server")
        proc.daemon = True
        proc.start()
        logger.info(f"[Started] inference_server pid={proc.pid}")
        return proc

    p_server = _spawn_inference()
    
    # Start Camera Workers
    cam_dirs = {}
    worker_configs: dict[str, dict] = {}
    worker_processes: dict[str, multiprocessing.Process] = {}

    def _spawn_worker(cam_id: str) -> multiprocessing.Process:
        kwargs = dict(worker_configs[cam_id])
        proc = multiprocessing.Process(
            target=worker_camera_capture,
            kwargs=kwargs,
            name=f"camera_worker_{cam_id}",
        )
        proc.daemon = True
        proc.start()
        worker_processes[cam_id] = proc
        logger.info(f"[Started] {cam_id} pid={proc.pid} -> {kwargs['source_url']}")
        return proc

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

        worker_configs[cam_id] = worker_kwargs
        _spawn_worker(cam_id)

    # Aggregator
    aggregator = OutletAggregator(
        outlet_id, 
        absent_seconds=settings.presence.absent_seconds,
        target_spg_ids=target_spg_ids
    )
    
    event_stores = {cid: EventStore(d) for cid, d in cam_dirs.items()}
    snapshot_store = SnapshotStore(settings.storage.data_dir) # Initialize snapshot store
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
            "capture_to_inference_ema_ms": None,
            "input_queue_wait_ema_ms": None,
            "post_inference_queue_ema_ms": None,
        }
        for cam_id, src in camera_sources
    }
    result_windows = {cam_id: deque(maxlen=120) for cam_id, _ in camera_sources}
    worker_restart_histories = {cam_id: deque() for cam_id, _ in camera_sources}
    worker_last_restart_ts = {cam_id: 0.0 for cam_id, _ in camera_sources}
    worker_restart_exhausted: set[str] = set()
    inference_restart_history: deque[float] = deque()
    inference_last_restart_ts = 0.0
    hit_streaks_by_camera: dict[str, dict[str, int]] = {cam_id: {} for cam_id, _ in camera_sources}

    high_lag_streak = 0
    low_lag_streak = 0
    
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
            # Send startup signal
            mode_str = "SIMULATION" if use_simulation else "PRODUCTION"
            startup_msg = (
                f"🟢 **Monitoring Started**\n"
                f"Outlet: {outlet_id}\n"
                f"Mode: {mode_str}\n"
                f"Cameras: {len(camera_sources)}\n"
                f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            try:
                notifier.send_message(startup_msg)
            except Exception as e:
                logger.warning(f"Failed to send startup telegram: {e}")

        except Exception as e:
            logger.warning(f"Telegram notifier disabled: {e}")
    else:
        logger.info("Telegram notification disabled in config.")
    
    logger.info("[Main] Centralized Loop active.")
    state_path = os.path.join(base_data_dir, "outlet_state.json")
    health_path = os.path.join(base_data_dir, "camera_health.json")
    
    try:
        while True:
            loop_now = time.time()
            _apply_runtime_control()

            # Inference process
            if not p_server.is_alive():
                if (loop_now - inference_last_restart_ts) >= restart_cooldown_sec and _restart_allowed(
                    inference_restart_history, max_restarts_per_minute
                ):
                    logger.error("[Supervisor] Inference process died. Restarting...")
                    _terminate_process(p_server, "inference_server")
                    p_server = _spawn_inference()
                    inference_last_restart_ts = loop_now
                elif (loop_now - inference_last_restart_ts) >= restart_cooldown_sec:
                    logger.critical("[Supervisor] Inference restart budget exhausted. Stopping pipeline.")
                    break

            # Camera workers (per-camera recovery)
            for cam_id, proc in list(worker_processes.items()):
                if cam_id in worker_restart_exhausted:
                    continue
                if proc.is_alive():
                    continue

                if (loop_now - worker_last_restart_ts.get(cam_id, 0.0)) < restart_cooldown_sec:
                    continue

                hist = worker_restart_histories.get(cam_id)
                if hist is None:
                    hist = deque()
                    worker_restart_histories[cam_id] = hist

                if not _restart_allowed(hist, max_restarts_per_minute):
                    worker_restart_exhausted.add(cam_id)
                    logger.critical(f"[Supervisor] Worker {cam_id} restart budget exhausted.")
                    continue

                logger.error(f"[Supervisor] Worker {cam_id} died. Restarting...")
                _terminate_process(proc, f"worker_{cam_id}")
                worker_last_restart_ts[cam_id] = loop_now
                _spawn_worker(cam_id)

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

                        cap_to_inf_ms = float(res.get("capture_to_inference_ms", lag_ms))
                        prev_cap_inf = metrics["capture_to_inference_ema_ms"]
                        metrics["capture_to_inference_ema_ms"] = (
                            cap_to_inf_ms
                            if prev_cap_inf is None
                            else (0.2 * cap_to_inf_ms + 0.8 * prev_cap_inf)
                        )

                        in_q_wait_ms = float(res.get("input_queue_wait_ms", 0.0))
                        prev_in_q = metrics["input_queue_wait_ema_ms"]
                        metrics["input_queue_wait_ema_ms"] = (
                            in_q_wait_ms
                            if prev_in_q is None
                            else (0.2 * in_q_wait_ms + 0.8 * prev_in_q)
                        )

                        inf_done_ts = float(res.get("inference_done_ts", now_ts))
                        post_inf_q_ms = max(0.0, (now_ts - inf_done_ts) * 1000.0)
                        prev_post_q = metrics["post_inference_queue_ema_ms"]
                        metrics["post_inference_queue_ema_ms"] = (
                            post_inf_q_ms
                            if prev_post_q is None
                            else (0.2 * post_inf_q_ms + 0.8 * prev_post_q)
                        )
                    
                    if cid in worker_feedback_queues:
                        try:
                            worker_feedback_queues[cid].put_nowait(res)
                        except queue.Full:
                            pass

                    candidates_by_spg: dict[str, dict] = {}
                    for f in res['faces']:
                        if not f.get("matched"):
                            continue
                        spg_id = f.get("spg_id")
                        if spg_id not in target_spg_set:
                            continue

                        prev = candidates_by_spg.get(spg_id)
                        if prev is None or float(f.get("similarity", 0.0)) > float(prev.get("similarity", 0.0)):
                            candidates_by_spg[spg_id] = f

                    streaks = hit_streaks_by_camera.setdefault(cid, {})
                    seen_spg_ids = set(candidates_by_spg.keys())

                    for spg_id, f in candidates_by_spg.items():
                        streak_now = streaks.get(spg_id, 0) + 1
                        streaks[spg_id] = streak_now
                        current_min_hits = max(1, int(min_hits_control.value))
                        if streak_now < current_min_hits:
                            continue

                        ev = Event(
                            event_type="SPG_SEEN",
                            outlet_id=outlet_id,
                            camera_id=cid,
                            spg_id=spg_id,
                            name=f.get("name"),
                            similarity=float(f.get("similarity", 0.0)),
                            ts=res['timestamp'],
                            details={"frame_id": res['frame_id'], "consecutive_hits": streak_now},
                        )
                        if cid in event_stores:
                            event_stores[cid].append(ev)
                        events_batch.append(ev)
                        if metrics is not None:
                            metrics["events_count"] += 1
                            metrics["last_event_ts"] = float(res.get("timestamp", now_ts))

                    for spg_id in list(streaks.keys()):
                        if spg_id not in seen_spg_ids:
                            streaks.pop(spg_id, None)

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

                        snapshot_path = None
                        for cid in cam_dirs:
                             possible_path = os.path.join(cam_dirs[cid], "snapshots", "latest_frame.jpg")
                             if os.path.exists(possible_path):
                                 try:
                                     frame = cv2.imread(possible_path)
                                     if frame is not None:
                                         snapshot_path = snapshot_store.save_alert_frame(outlet_id, cid, frame)
                                         break
                                 except Exception:
                                     pass
                        
                        if snapshot_path:
                            notifier.send_photo(snapshot_path, caption=f"📸 Snapshot at {ts_str}")
                            
                    except Exception as e:
                        logger.warning(f"Failed to send telegram alert: {e}")
                        pass

            if auto_degrade_enabled:
                lag_samples = []
                for cam_id, m in camera_metrics.items():
                    if cam_id in worker_restart_exhausted:
                        continue
                    lag_val = m.get("queue_lag_ema_ms")
                    if lag_val is None:
                        continue
                    lag_num = float(lag_val)
                    if lag_num > 0:
                        lag_samples.append(lag_num)

                if lag_samples:
                    avg_lag_ms = sum(lag_samples) / len(lag_samples)
                    if avg_lag_ms >= auto_degrade_lag_high_ms:
                        high_lag_streak += 1
                        low_lag_streak = 0
                    elif avg_lag_ms <= auto_degrade_lag_low_ms:
                        low_lag_streak += 1
                        high_lag_streak = 0
                    else:
                        high_lag_streak = 0
                        low_lag_streak = 0

                    current_skip = int(frame_skip_control.value)
                    if high_lag_streak >= auto_degrade_high_streak_target and current_skip < auto_degrade_max_skip:
                        frame_skip_control.value = current_skip + 1
                        logger.warning(
                            f"[AutoDegrade] High lag avg={avg_lag_ms:.1f}ms "
                            f"-> frame_skip {current_skip} -> {int(frame_skip_control.value)}"
                        )
                        high_lag_streak = 0
                        low_lag_streak = 0
                    elif low_lag_streak >= auto_degrade_low_streak_target and current_skip > frame_skip_base:
                        frame_skip_control.value = current_skip - 1
                        logger.info(
                            f"[AutoDegrade] Lag recovered avg={avg_lag_ms:.1f}ms "
                            f"-> frame_skip {current_skip} -> {int(frame_skip_control.value)}"
                        )
                        high_lag_streak = 0
                        low_lag_streak = 0

            health_now = time.time()
            health_payload = {
                "timestamp": health_now,
                "outlet_id": outlet_id,
                "frame_skip": int(frame_skip_control.value),
                "base_frame_skip": int(frame_skip_base),
                "min_consecutive_hits": int(min_hits_control.value),
                "min_det_score": round(float(min_det_score_control.value), 4),
                "min_face_width_px": int(min_face_width_control.value),
                "auto_degrade_enabled": auto_degrade_enabled,
                "runtime_control_path": control_path,
                "supervisor": {
                    "inference_alive": p_server.is_alive(),
                    "inference_restarts_last_minute": len(inference_restart_history),
                    "worker_restart_exhausted": sorted(worker_restart_exhausted),
                },
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
                if result_age_sec is None or result_age_sec > 2.0:
                    processed_fps = 0.0

                if result_age_sec is None or result_age_sec > 10.0:
                    status = "OFFLINE"
                elif result_age_sec > 2.0:
                    status = "STALE"
                else:
                    status = "LIVE"

                worker_alive = False
                proc = worker_processes.get(cam_id)
                if proc is not None:
                    worker_alive = proc.is_alive()
                if cam_id in worker_restart_exhausted:
                    status = "OFFLINE"

                health_payload["cameras"].append(
                    {
                        "camera_id": cam_id,
                        "source_type": m.get("source_type", _source_type(src)),
                        "status": status,
                        "worker_alive": worker_alive,
                        "restart_exhausted": cam_id in worker_restart_exhausted,
                        "worker_restarts_last_minute": len(worker_restart_histories.get(cam_id, deque())),
                        "processed_fps": round(processed_fps, 2),
                        "inference_time_ms": round(float(m.get("inference_time_ema_ms") or 0.0), 1),
                        "queue_lag_ms": round(float(m.get("queue_lag_ema_ms") or 0.0), 1),
                        "capture_to_inference_ms": round(float(m.get("capture_to_inference_ema_ms") or 0.0), 1),
                        "input_queue_wait_ms": round(float(m.get("input_queue_wait_ema_ms") or 0.0), 1),
                        "post_inference_queue_ms": round(float(m.get("post_inference_queue_ema_ms") or 0.0), 1),
                        "last_result_age_sec": None if result_age_sec is None else round(result_age_sec, 2),
                        "last_frame_id": int(m.get("last_frame_id") or 0),
                        "events_count": int(m.get("events_count") or 0),
                    }
                )
            _safe_write_json(health_path, health_payload)
            
            aggregator.dump_state(state_path)
                
            time.sleep(settings.runtime.main_loop_sleep_sec)

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        _terminate_process(p_server, "inference_server")
        for cam_id, proc in worker_processes.items():
            _terminate_process(proc, f"worker_{cam_id}")
        for buf in shared_buffers.values():
            buf.close()
            buf.unlink()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    args = parser.parse_args()
    
    run_outlet(
        preview=(args.preview and not args.no_preview),
        force_simulate=args.simulate,
        config_path=args.config,
    )
