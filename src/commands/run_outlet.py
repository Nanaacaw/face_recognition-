import multiprocessing
import time
import os
import json
import signal
from typing import List

from src.commands.run_webcam import run_webcam_recognition
from src.pipeline.outlet_aggregator import OutletAggregator
from src.domain.events import Event

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
            preview=True, 
            loop_video=True,
            gallery_dir="data" 
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[Worker {camera_id}] Failed: {e}")

def run_outlet_simulation(
    outlet_id: str, 
    video_files: List[str], 
    base_data_dir: str
):
    print(f"=== Simulation Started: {outlet_id} ===")
    
    # Common Config (Hardcoded for simulation simplicity)
    config_common = {
        'process_fps': 10,
        'threshold': 0.40,
        'grace_seconds': 5,
        'absent_seconds': 15,
        'outlet_id': outlet_id,
        'target_spg_ids': ['001', '002']
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
        absent_seconds=config_common['absent_seconds']
    )
    
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
                print(f"\n🔥🔥🔥 [GLOBAL ALERT] SPG {al.spg_id} is ABSENT from OUTLET! 🔥🔥🔥")
                print(al.model_dump_json(indent=2))
            
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
        
    run_outlet_simulation(args.outlet, valid_videos, args.data_dir)
