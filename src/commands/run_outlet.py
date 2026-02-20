import multiprocessing
import time
import os
import json
import sys

from src.commands.run_webcam import run_webcam_recognition
from src.pipeline.outlet_aggregator import OutletAggregator
from src.domain.events import Event
from src.notification.telegram_notifier import TelegramNotifier
from src.settings.settings import load_settings
from dotenv import load_dotenv


from src.settings.logger import logger
from src.storage.snapshot_cleaner import SnapshotCleaner

def worker_camera_process(config_common, camera_id, source_url, data_dir):
    """
    Runs a single camera pipeline in a separate process.
    source_url can be an RTSP URL, a local video file path, or "0"/"1" for webcam.
    """
    logger.info(f"[Worker {camera_id}] Starting with source: {source_url}")
    
    os.makedirs(data_dir, exist_ok=True)

    camera_source = "rtsp"
    rtsp_url = source_url
    webcam_index = 0

    if source_url == "webcam" or (isinstance(source_url, str) and source_url.isdigit()):
        camera_source = "webcam"
        webcam_index = int(source_url) if source_url.isdigit() else 0
        rtsp_url = None
        logger.info(f"[Worker {camera_id}] Mode: WEBCAM (index={webcam_index})")
    else:
        logger.info(f"[Worker {camera_id}] Mode: RTSP/FILE ({source_url})")

    try:
        run_webcam_recognition(
            data_dir=data_dir,
            webcam_index=webcam_index, 
            process_fps=config_common['process_fps'],
            threshold=config_common['threshold'],
            grace_seconds=config_common['grace_seconds'],
            absent_seconds=config_common['absent_seconds'],
            outlet_id=config_common['outlet_id'],
            camera_id=camera_id,
            target_spg_ids=config_common['target_spg_ids'],
            camera_source=camera_source,
            rtsp_url=rtsp_url,
            preview=config_common['preview'], 
            loop_video=config_common.get('loop_video', False),
            gallery_dir="data", 
            enable_notifier=False,
            model_name=config_common['model_name'],
            execution_providers=config_common['execution_providers'],
            det_size=config_common['det_size'],
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"[Worker {camera_id}] Failed: {e}", exc_info=True)


def run_outlet(preview: bool = False, force_simulate: bool = False):
    """
    Main multi-camera outlet runner.
    
    Modes:
      --simulate flag (or force_simulate=True) → always use video files
      Otherwise → use outlet.cameras RTSP URLs from config
    """
    settings = load_settings()
    
    # Resolve outlet config
    if settings.outlet is None:
        logger.error("No 'outlet' section found in config. Cannot run multi-camera mode.")
        sys.exit(1)
    
    outlet = settings.outlet
    outlet_id = outlet.id
    target_spg_ids = outlet.target_spg_ids
    
    logger.info(f"=== Outlet Started: {outlet_id} ({outlet.name}) ===")
    logger.info(f"[Config] Target SPG IDs: {target_spg_ids}")
    
    use_simulation = force_simulate or settings.dev.simulate
    camera_sources = []  # List of (camera_id, source_url)
    loop_video = False
    
    if use_simulation and settings.dev.video_files:
        logger.info(f"[Mode] SIMULATION — using {len(settings.dev.video_files)} video file(s)")
        loop_video = True
        for i, vf in enumerate(settings.dev.video_files):
            if not os.path.exists(vf):
                logger.warning(f"Video file not found: {vf}")
                continue
            cam_id = f"cam_{i+1:02d}"
            camera_sources.append((cam_id, vf))
    else:
        logger.info(f"[Mode] PRODUCTION — using {len(outlet.cameras)} RTSP camera(s)")
        for cam in outlet.cameras:
            camera_sources.append((cam.id, cam.rtsp_url))
    
    if not camera_sources:
        logger.error("No valid camera sources. Check config.")
        sys.exit(1)
    
    config_common = {
        'process_fps': settings.camera.process_fps,
        'threshold': settings.recognition.threshold,
        'grace_seconds': settings.presence.grace_seconds,
        'absent_seconds': settings.presence.absent_seconds,
        'outlet_id': outlet_id,
        'target_spg_ids': target_spg_ids,
        'preview': preview,
        'loop_video': loop_video,
        'model_name': settings.recognition.model_name,
        'execution_providers': settings.recognition.execution_providers,
        'det_size': settings.recognition.det_size,
    }

    base_data_dir = os.path.join(settings.storage.data_dir, "sim_output")
    os.makedirs(base_data_dir, exist_ok=True)
    
    old_state = os.path.join(base_data_dir, "outlet_state.json")
    if os.path.exists(old_state):
        os.remove(old_state)
        logger.info("[Cleanup] Removed old outlet_state.json")
    
    # Run Snapshot Cleaner (Startup)
    try:
        cleaner = SnapshotCleaner(
            data_dir=settings.storage.data_dir,
            retention_days=settings.storage.snapshot_retention_days
        )
        cleaner.clean()
    except Exception as e:
        logger.error(f"[Cleanup] Snapshot cleaning failed: {e}")
    
    # 1. Start Worker Processes
    processes = []
    cam_data_dirs = []
    
    for cam_id, source_url in camera_sources:
        d_dir = os.path.join(base_data_dir, cam_id)
        cam_data_dirs.append(d_dir)
        
        p = multiprocessing.Process(
            target=worker_camera_process,
            args=(config_common, cam_id, source_url, d_dir)
        )
        p.daemon = True
        p.start()
        processes.append(p)
        logger.info(f"[Started] {cam_id} -> {source_url}")

    # 2. Setup Aggregator
    aggregator = OutletAggregator(
        outlet_id, 
        absent_seconds=config_common['absent_seconds'],
        target_spg_ids=target_spg_ids
    )
    
    # 3. Setup Telegram
    load_dotenv()
    
    token = os.getenv("SPG_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("SPG_TELEGRAM_CHAT_ID")
    token_status = "OK" if token else "MISSING"
    chat_status = "OK" if chat_id else "MISSING"
    logger.info(f"[Telegram] Token: {token_status}, Chat-ID: {chat_status}")
    
    notifier = None
    try:
        notifier = TelegramNotifier.from_env()
        logger.info("[Telegram] Notifier ready.")
    except Exception as e:
        logger.warning(f"[Telegram] Disabled: {e}")

    # 4. Main Aggregator Loop
    logger.info(f"[Aggregator] Monitoring {len(camera_sources)} cameras...")
    
    event_files = [os.path.join(d, "events.jsonl") for d in cam_data_dirs]
    file_pointers = {}
    state_path = os.path.join(base_data_dir, "outlet_state.json")

    try:
        while True:
            events_batch = []
            
            for ef in event_files:
                if not os.path.exists(ef):
                    continue
                
                if ef not in file_pointers:
                    f = open(ef, 'r')
                    f.seek(0, 2)
                    file_pointers[ef] = f
                
                f = file_pointers[ef]
                line = f.readline()
                while line:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            ev = Event(**data)
                            events_batch.append(ev)
                        except Exception:
                            logger.warning(f"Failed to parse event line from {ef}", exc_info=False)
                    line = f.readline()
            
            if events_batch:
                aggregator.ingest_events(events_batch)
            
            alerts = aggregator.tick()
            for al in alerts:

                snap_path = None
                for d in cam_data_dirs:
                    p = os.path.join(d, "snapshots", f"latest_{al.spg_id}.jpg")
                    if os.path.exists(p):
                        snap_path = p
                        break
                
                # Build alert message
                reason = al.details.get("reason", "global_absence")
                duration = al.details.get("seconds_since_last_seen") or al.details.get("seconds_since_startup", "?")
                
                title = "⚠️ **SPG ABSENCE DETECTED** ⚠️"
                if reason == "startup_absence_never_arrived":
                     title = "🚫 **PERSONNEL NEVER ARRIVED** 🚫"
                
                spg_name = al.name or "Unknown"
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(al.ts))
                
                text = (
                    f"{title}\n\n"
                    f"📍 **Outlet:** {al.outlet_id}\n"
                    f"👤 **Personnel:** {spg_name} ({al.spg_id})\n"
                    f"⏱️ **Duration:** {duration}s\n"
                    f"🕒 **Time:** {timestamp}\n"
                )    
                # logger.warning(f"ALERT FIRED | Outlet: {al.outlet_id} | SPG: {al.spg_id} | Reason: {reason}")
                
                if notifier:
                    try:
                        if snap_path:
                            notifier.send_photo(snap_path, caption=text)
                        else:
                            notifier.send_message(text)
                    except Exception as ex:
                        logger.error(f"[Telegram] Failed to send alert: {ex}")
            
            # Dump state for dashboard
            aggregator.dump_state(state_path)
            
            # Check worker health
            if not any(p.is_alive() for p in processes):
                logger.info("All workers finished/died.")
                break          
                
            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Stopping...")
        for p in processes:
            p.terminate()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Multi-Camera Outlet Monitoring")
    parser.add_argument("--preview", action="store_true", help="Show video preview windows")
    parser.add_argument("--no-preview", action="store_true", help="Disable video preview (for servers)")
    parser.add_argument("--simulate", action="store_true", help="Force simulation mode (use video files)")
    
    args = parser.parse_args()
    
    show_preview = args.preview and not args.no_preview
    
    run_outlet(preview=show_preview, force_simulate=args.simulate)
