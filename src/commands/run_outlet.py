import multiprocessing
import time
import os
import json
import signal
from typing import List

from src.commands.run_webcam import run_webcam_recognition
from src.pipeline.outlet_aggregator import OutletAggregator
from src.domain.events import Event
from src.commands.run_webcam import run_webcam_recognition
from src.pipeline.outlet_aggregator import OutletAggregator
from src.domain.events import Event
from src.notification.telegram_notifier import TelegramNotifier
from src.settings.settings import load_settings
from dotenv import load_dotenv

def worker_camera_process(config_common, camera_id, video_path, data_dir):
    """
    Runs a single camera pipeline in a separate process.
    """
    print(f"[Worker {camera_id}] Starting with video {video_path}")
    
    os.makedirs(data_dir, exist_ok=True)

    try:
        run_webcam_recognition(
            data_dir=data_dir,
            webcam_index=0, 
            process_fps=config_common['process_fps'],
            threshold=config_common['threshold'],
            grace_seconds=config_common['grace_seconds'],
            absent_seconds=config_common['absent_seconds'],
            outlet_id=config_common['outlet_id'],
            camera_id=camera_id,
            target_spg_ids=config_common['target_spg_ids'],
            camera_source="rtsp",
            rtsp_url=video_path,
            preview=config_common['preview'], 
            loop_video=True,
            gallery_dir="data", 
            enable_notifier=False
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[Worker {camera_id}] Failed: {e}")

def run_outlet_simulation(
    outlet_id: str, 
    video_files: List[str], 
    base_data_dir: str,
    preview: bool = True
):
    
    print(f"=== Simulation Started: {outlet_id} ===")
    settings = load_settings()
    
    # Use config values, but override outlet_id if provided in args
    # (The script arg default is 'outlet_mkg', config is 'OUTLET_DEV')
    # We'll use the script argument as the source of truth for outlet_id since it's an explicit input.
    
    print(f"[Config] Loaded SPG IDs: {settings.target.spg_ids}")
    
    config_common = {
        'process_fps': 5, # Reduced from 10 to 5 to save CPU
        'threshold': settings.recognition.threshold,
        'threshold': settings.recognition.threshold,
        'grace_seconds': settings.presence.grace_seconds,
        'absent_seconds': settings.presence.absent_seconds,
        'outlet_id': outlet_id,
        'target_spg_ids': settings.target.spg_ids,
        'preview': preview
    }

    processes = []
    cam_data_dirs = []

    os.makedirs(base_data_dir, exist_ok=True)
    
    # 1. Start Workers
    for i, video_file in enumerate(video_files):
        cam_id = f"cam_{i+1:02d}"
        d_dir = os.path.join(base_data_dir, cam_id)
        cam_data_dirs.append(d_dir)
        
        p = multiprocessing.Process(
            target=worker_camera_process,
            args=(config_common, cam_id, video_file, d_dir)
        )
        p.daemon = True
        p.start()
        processes.append(p)

    # 2. Aggregator Loop (Main Process)
    aggregator = OutletAggregator(
        outlet_id, 
        absent_seconds=config_common['absent_seconds'],
        target_spg_ids=config_common['target_spg_ids']
    )
    
    # Initialize Telegram Notifier
    load_dotenv()
    
    token = os.getenv("SPG_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("SPG_TELEGRAM_CHAT_ID")
    print(f"[DEBUG] Env Check - Token found: {bool(token)}, Chat-ID found: {bool(chat_id)}")
    
    notifier = None
    try:
        notifier = TelegramNotifier.from_env()
        print("[Setup] Telegram notifier initialized successfully.")
        notifier.send_message(f"🚀 Simulation Started: {outlet_id}\nChecking Telegram Connection...")
    except Exception as e:
        print(f"[WARN] Telegram integration disabled: {e}")

    print("[Aggregator] Monitoring events...")
    
    event_files = [os.path.join(d, "events.jsonl") for d in cam_data_dirs]
    file_pointers = {}

    try:
        while True:
            events_batch = []
            
            for ef in event_files:
                if not os.path.exists(ef):
                    continue
                
                if ef not in file_pointers:
                    f = open(ef, 'r')
                    f.seek(0, 2) # Seek to end (tail)
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
                            pass
                    line = f.readline()
            
            # Feed aggregator
            if events_batch:
                aggregator.ingest_events(events_batch)
                # print(f"[Aggregator] Ingested {len(events_batch)} events")
            
            # Tick logic
            alerts = aggregator.tick()
            for al in alerts:
                # Try to find a snapshot in any camera folder
                snap_path = None
                for d in cam_data_dirs:
                    p = os.path.join(d, "snapshots", f"latest_{al.spg_id}.jpg")
                    if os.path.exists(p):
                        # Pick the first one found, or maybe check timestamps if needed.
                        # For now, any recent snapshot is better than none.
                        snap_path = p
                        break
                
                # Construct Message
                reason = al.details.get("reason", "global_absence")
                duration = al.details.get("seconds_since_last_seen") or al.details.get("seconds_since_startup", "?")
                
                title = "⚠️ **SPG ABSENCE DETECTED** ⚠️"
                if reason == "startup_absence_never_arrived":
                     title = "🚫 **PERSONNEL NEVER ARRIVED** 🚫"
                
                spg_name = al.name or "Unknown"
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                
                text = (
                    f"{title}\n\n"
                    f"📍 **Outlet:** {al.outlet_id}\n"
                    f"👤 **Personnel:** {spg_name} ({al.spg_id})\n"
                    f"⏱️ **Duration:** {duration}s\n"
                    f"🕒 **Time:** {timestamp}\n"
                )
                print(text)
                print(al.model_dump_json(indent=2))
                
                if notifier:
                    print(f"[DEBUG] Attempting to send Telegram alert for SPG {al.spg_id}...")
                    try:
                        if snap_path:
                            print(f"[DEBUG] Sending photo: {snap_path}")
                            notifier.send_photo(snap_path, caption=text)
                        else:
                            print(f"[DEBUG] Sending text only.")
                            notifier.send_message(text)
                        print("[DEBUG] Telegram sent successfully.")
                    except Exception as ex:
                        print(f"[ERROR] Failed to send Telegram: {ex}")
                else:
                    print("[DEBUG] Notifier is OFF/None. Check .env and startup logs.")
            
            # Check worker health
            if not any(p.is_alive() for p in processes):
                print("All workers finished/died.")
                break
                
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopping simulation...")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Simulate Outlet Multi-Camera Aggregation")
    parser.add_argument("videos", nargs="+", help="List of video file paths to simulate cameras")
    parser.add_argument("--outlet", default="outlet_mkg", help="Outlet ID")
    parser.add_argument("--data-dir", default="data/sim_output", help="Output directory")
    parser.add_argument("--no-preview", action="store_true", help="Disable video preview windows to save resources")

    args = parser.parse_args()
    
    # Verify files
    valid_videos = []
    for v in args.videos:
        if os.path.exists(v):
            valid_videos.append(v)
        else:
            print(f"[WARN] Video not found: {v}")
    
    if not valid_videos:
        print("No valid video files provided.")
        sys.exit(1)
        
    run_outlet_simulation(args.outlet, valid_videos, args.data_dir, not args.no_preview)
