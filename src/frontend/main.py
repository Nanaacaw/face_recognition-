import json
import os
import glob
import time
from datetime import datetime
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

# ── Config ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data", "sim_output")

app = FastAPI(title="SPG Dashboard", version="2.0")

# CORS (allow all for dev convenience)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


# ── Helpers ──

def get_state():
    path = os.path.join(DATA_DIR, "outlet_state.json")
    if not os.path.exists(path):
        return {"status": "waiting", "outlet_id": "Unknown", "spgs": []}
    
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_recent_events(limit=50):
    events = []
    # Scan all camera directories
    pattern = os.path.join(DATA_DIR, "cam_*", "events.jsonl")
    files = glob.glob(pattern)
    
    for ef in files:
        cam_id = os.path.basename(os.path.dirname(ef))
        try:
            with open(ef, "r") as f:
                # Read last N lines for efficiency (simple approach)
                lines = f.readlines()
                for line in lines[-limit:]:
                    if line.strip():
                        try:
                            ev = json.loads(line)
                            ev["_camera"] = cam_id
                            events.append(ev)
                        except:
                            pass
        except:
            pass
            
    # Sort by timestamp descending
    events.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return events[:limit]

def find_spg_snapshot(spg_id):
    # Find latest snapshot across all cameras for this SPG
    pattern = os.path.join(DATA_DIR, "cam_*", "snapshots", f"latest_{spg_id}.jpg")
    files = glob.glob(pattern)
    if not files:
        return None
    # Return newest file
    return max(files, key=os.path.getmtime)

def get_camera_frame(cam_id):
    path = os.path.join(DATA_DIR, cam_id, "snapshots", "latest_frame.jpg")
    if os.path.exists(path):
        return path
    return None

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/state")
async def api_state():
    state = get_state()
    # Enrich SPG data with snapshot URL
    if "spgs" in state:
        for spg in state["spgs"]:
            spg_id = spg.get("id")
            # Check if snapshot exists
            snap_path = find_spg_snapshot(spg_id)
            if snap_path:
                spg["snapshot_url"] = f"/api/snapshot/{spg_id}"
            else:
                spg["snapshot_url"] = None
    
    # Check system liveness
    last_ts = state.get("timestamp", 0)
    is_live = (time.time() - last_ts) < 10
    state["system_status"] = "LIVE" if is_live else "OFFLINE"
    
    return state

@app.get("/api/events")
async def api_events():
    return get_recent_events()

@app.get("/api/snapshot/{spg_id}")
async def api_snapshot(spg_id: str):
    path = find_spg_snapshot(spg_id)
    if path:
        return FileResponse(path)
    return Response(status_code=404)

@app.get("/api/cameras")
async def api_cameras():
    # List available cameras
    cams = []
    pattern = os.path.join(DATA_DIR, "cam_*")
    dirs = glob.glob(pattern)
    for d in dirs:
        if os.path.isdir(d):
            cam_id = os.path.basename(d)
            cams.append({
                "id": cam_id,
                "stream_url": f"/stream/{cam_id}"
            })
    return cams

# ── Streaming ──

def mjpeg_generator(cam_id):
    """Yields MJPEG stream from latest_frame.jpg"""
    file_path = os.path.join(DATA_DIR, cam_id, "snapshots", "latest_frame.jpg")
    
    while True:
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    frame_data = f.read()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                
                # Sleep to limit FPS and CPU usage
                time.sleep(0.2) # 5 FPS is enough for monitoring dashboard
            except Exception:
                time.sleep(0.5)
        else:
            time.sleep(1.0)

@app.get("/stream/{cam_id}")
async def stream_feed(cam_id: str):
    return StreamingResponse(
        mjpeg_generator(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

if __name__ == "__main__":
    import uvicorn
    # Run with reload for dev convenience
    uvicorn.run("src.frontend.main:app", host="0.0.0.0", port=8000, reload=True)
