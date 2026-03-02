import json
import os
import glob
import time
from collections import deque

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from src.pipeline.face_detector import FaceDetector
from src.settings.settings import load_settings

SETTINGS = load_settings()
DATA_DIR = os.path.join(SETTINGS.storage.data_dir, SETTINGS.storage.sim_output_subdir)
GALLERY_DIR = os.path.join(SETTINGS.storage.data_dir, SETTINGS.storage.gallery_subdir)
HEALTH_PATH = os.path.join(DATA_DIR, "camera_health.json")
RUNTIME_CONTROL_PATH = os.path.join(DATA_DIR, "runtime_control.json")

if not os.path.exists(DATA_DIR):
    print(f"Warning: {DATA_DIR} does not exist yet. Dashboard might be empty.")
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_configured_camera_ids() -> set[str]:
    """Return a set of camera IDs present in the current configuration."""
    ids = set()
    if SETTINGS.outlet and SETTINGS.outlet.cameras:
        for cam in SETTINGS.outlet.cameras:
            if cam.id:
                ids.add(cam.id)
    
    if SETTINGS.target and SETTINGS.target.camera_id:
        ids.add(SETTINGS.target.camera_id)
        
    return ids


app = FastAPI(title="SPG Dashboard", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def get_state():
    path = os.path.join(DATA_DIR, "outlet_state.json")
    if not os.path.exists(path):
        return {"status": "waiting", "outlet_id": "Unknown", "spgs": []}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_health():
    if not os.path.exists(HEALTH_PATH):
        return {"timestamp": 0, "outlet_id": "Unknown", "cameras": []}

    try:
        with open(HEALTH_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {"timestamp": 0, "outlet_id": "Unknown", "cameras": []}

    if not isinstance(payload, dict):
        return {"timestamp": 0, "outlet_id": "Unknown", "cameras": []}
    payload.setdefault("cameras", [])
    payload.setdefault("timestamp", 0)
    payload.setdefault("outlet_id", "Unknown")
    return payload


def get_recent_events(limit: int | None = None):
    limit = limit or SETTINGS.dashboard.recent_events_limit
    events = []
    pattern = os.path.join(DATA_DIR, "cam_*", "events.jsonl")
    files = glob.glob(pattern)

    active_ids = _get_configured_camera_ids()
    valid_files = []
    for ef in files:
        cam_id = os.path.basename(os.path.dirname(ef))
        if cam_id in active_ids:
            valid_files.append(ef)
            
    for ef in valid_files:
        cam_id = os.path.basename(os.path.dirname(ef))
        try:
            with open(ef, "r", encoding="utf-8") as f:
                recent_lines = deque(f, maxlen=limit)

            for line in recent_lines:
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                    ev["_camera"] = cam_id
                    events.append(ev)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass

    events.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return events[:limit]

def find_spg_snapshot(spg_id):
    pattern = os.path.join(DATA_DIR, "cam_*", "snapshots", f"latest_{spg_id}.jpg")
    files = glob.glob(pattern)
    if not files:
        return None
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
    health = get_health()
    if "spgs" in state:
        for spg in state["spgs"]:
            spg_id = spg.get("id")
            snap_path = find_spg_snapshot(spg_id)
            if snap_path:
                spg["snapshot_url"] = f"/api/snapshot/{spg_id}"
            else:
                spg["snapshot_url"] = None
    
    last_ts = state.get("timestamp", 0)
    is_live = (time.time() - last_ts) < SETTINGS.dashboard.live_window_seconds
    state["system_status"] = "LIVE" if is_live else "OFFLINE"
    state["camera_health"] = health.get("cameras", [])
    state["camera_health_timestamp"] = health.get("timestamp", 0)
    
    return state

@app.get("/api/events")
async def api_events():
    return get_recent_events()


@app.get("/api/health")
async def api_health():
    return get_health()


@app.get("/api/runtime/control")
async def api_runtime_control_get():
    defaults = {
        "frame_skip": 0,
        "min_consecutive_hits": 1,
        "min_det_score": 0.0,
        "min_face_width_px": 0,
        "auto_degrade_enabled": True,
        "control_path": RUNTIME_CONTROL_PATH,
    }
    try:
        if os.path.exists(RUNTIME_CONTROL_PATH):
            with open(RUNTIME_CONTROL_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, dict):
                    defaults.update(payload)
    except Exception:
        pass
    return defaults


@app.post("/api/runtime/control")
async def api_runtime_control_set(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return {"success": False, "error": "Invalid payload."}

    allowed_keys = {
        "frame_skip",
        "min_consecutive_hits",
        "min_det_score",
        "min_face_width_px",
        "auto_degrade_enabled",
    }
    sanitized: dict[str, int | float | bool] = {}
    for key in allowed_keys:
        if key not in payload:
            continue
        value = payload[key]
        try:
            if key in {"frame_skip", "min_consecutive_hits", "min_face_width_px"}:
                sanitized[key] = int(value)
            elif key == "min_det_score":
                sanitized[key] = float(value)
            elif key == "auto_degrade_enabled":
                sanitized[key] = bool(value)
        except (TypeError, ValueError):
            continue

    if not sanitized:
        return {"success": False, "error": "No valid control values."}

    # Read existing controls, then merge.
    current = {}
    if os.path.exists(RUNTIME_CONTROL_PATH):
        try:
            with open(RUNTIME_CONTROL_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    current = existing
        except Exception:
            current = {}
    current.update(sanitized)

    os.makedirs(os.path.dirname(RUNTIME_CONTROL_PATH), exist_ok=True)
    with open(RUNTIME_CONTROL_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)

    return {
        "success": True,
        "message": "Runtime control updated.",
        "control": current,
    }

@app.get("/api/snapshot/{spg_id}")
async def api_snapshot(spg_id: str):
    path = find_spg_snapshot(spg_id)
    if path:
        return FileResponse(path)
    return Response(status_code=404)

@app.get("/api/cameras")
async def api_cameras():
    cams = []
    active_ids = _get_configured_camera_ids()
    
    pattern = os.path.join(DATA_DIR, "cam_*")
    dirs = glob.glob(pattern)
    for d in dirs:
        if os.path.isdir(d):
            cam_id = os.path.basename(d)
            if cam_id not in active_ids:
                continue
            
            cams.append({
                "id": cam_id,
                "stream_url": f"/stream/{cam_id}",
                "ai_stream_url": f"/stream/{cam_id}",
                "raw_stream_url": f"/stream_raw/{cam_id}",
            })
    return cams


async def mjpeg_generator(cam_id: str, request: Request, filename: str):
    """Yields MJPEG stream from a snapshot file. Stops when client disconnects."""
    import asyncio
    file_path = os.path.join(DATA_DIR, cam_id, "snapshots", filename)
    last_good_frame: bytes | None = None

    while not await request.is_disconnected():
        frame_data = None
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    candidate = f.read()
                if candidate.startswith(b"\xff\xd8") and candidate.endswith(b"\xff\xd9"):
                    frame_data = candidate
                    last_good_frame = candidate
            except Exception:
                frame_data = None

        if frame_data is None:
            frame_data = last_good_frame

        if frame_data is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            await asyncio.sleep(SETTINGS.dashboard.stream_frame_interval_sec)
        else:
            await asyncio.sleep(SETTINGS.dashboard.stream_missing_frame_sleep_sec)

@app.get("/stream/{cam_id}")
async def stream_feed(cam_id: str, request: Request):
    return StreamingResponse(
        mjpeg_generator(cam_id, request, "latest_frame.jpg"),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stream_raw/{cam_id}")
async def stream_raw_feed(cam_id: str, request: Request):
    return StreamingResponse(
        mjpeg_generator(cam_id, request, "latest_raw_frame.jpg"),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


_detector_instance: "FaceDetector | None" = None

def _get_detector():
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = FaceDetector(
            name=SETTINGS.recognition.model_name,
            providers=SETTINGS.recognition.execution_providers,
            det_size=SETTINGS.recognition.det_size,
        )
        _detector_instance.start()
    return _detector_instance


@app.get("/manage")
async def manage_page(request: Request):
    return templates.TemplateResponse("manage.html", {"request": request})


@app.get("/api/gallery")
async def api_gallery_list():
    """List all enrolled SPGs."""
    from src.storage.gallery_store import GalleryStore
    store = GalleryStore(SETTINGS.storage.data_dir)
    gallery = store.load_all()

    result = []
    for spg_id, data in gallery.items():
        photo_path = os.path.join(GALLERY_DIR, f"{spg_id}_last_face.jpg")
        result.append({
            "spg_id": spg_id,
            "name": data.get("name", "Unknown"),
            "num_samples": len(data.get("embeddings", [])),
            "has_photo": os.path.exists(photo_path),
            "created_at": data.get("meta", {}).get("created_at"),
        })

    result.sort(key=lambda x: x["spg_id"])
    return result


@app.get("/api/gallery/{spg_id}/photo")
async def api_gallery_photo(spg_id: str):
    """Serve the face crop photo for an SPG."""
    path = os.path.join(GALLERY_DIR, f"{spg_id}_last_face.jpg")
    if os.path.exists(path):
        return FileResponse(path)
    return Response(status_code=404)


@app.post("/api/gallery/enroll")
async def api_gallery_enroll(request: Request):
    """
    Enroll a new SPG from uploaded photos.
    Expects multipart form: spg_id, name, files (1-5 images)
    """
    import cv2
    import numpy as np
    from src.enrollment.enroll_photo import enroll_from_photos
    from src.storage.gallery_store import GalleryStore

    form = await request.form()
    spg_id = form.get("spg_id", "").strip()
    name = form.get("name", "").strip()

    if not spg_id or not name:
        return {"success": False, "error": "spg_id dan name wajib diisi."}

    # Collect uploaded images
    images = []
    for key in form:
        if key.startswith("file"):
            upload = form[key]
            if hasattr(upload, "read"):
                raw = await upload.read()
                arr = np.frombuffer(raw, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    images.append(img)

    if not images:
        return {"success": False, "error": "Minimal 1 foto wajah diperlukan."}

    if len(images) > 5:
        images = images[:5]

    try:
        detector = _get_detector()
        payload, face_crop = enroll_from_photos(
            images=images,
            spg_id=spg_id,
            name=name,
            detector=detector,
        )

        store = GalleryStore(SETTINGS.storage.data_dir)
        store.save_person(spg_id, payload)

        if face_crop is not None:
            store.save_face_crop(spg_id, face_crop)

        return {
            "success": True,
            "spg_id": spg_id,
            "name": name,
            "num_samples": len(payload["embeddings"]),
        }

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Enrollment gagal: {str(e)}"}


@app.delete("/api/gallery/{spg_id}")
async def api_gallery_delete(spg_id: str):
    """Delete an SPG from gallery."""
    json_path = os.path.join(GALLERY_DIR, f"{spg_id}.json")
    photo_path = os.path.join(GALLERY_DIR, f"{spg_id}_last_face.jpg")

    deleted = False
    if os.path.exists(json_path):
        os.remove(json_path)
        deleted = True
    if os.path.exists(photo_path):
        os.remove(photo_path)

    if deleted:
        return {"success": True, "message": f"SPG {spg_id} dihapus."}
    return {"success": False, "error": f"SPG {spg_id} tidak ditemukan."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.frontend.main:app",
        host=SETTINGS.dashboard.host,
        port=SETTINGS.dashboard.port,
        reload=SETTINGS.dashboard.reload,
    )
