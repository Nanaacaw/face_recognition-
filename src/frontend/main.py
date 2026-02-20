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
from src.pipeline.face_detector import FaceDetector
from src.settings.settings import load_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_OUTPUT_DIR = os.path.join(BASE_DIR, "data", "sim_output")

if not os.path.exists(SIM_OUTPUT_DIR):
    print(f"Warning: {SIM_OUTPUT_DIR} does not exist yet. Dashboard might be empty.")
    os.makedirs(SIM_OUTPUT_DIR, exist_ok=True)

DATA_DIR = SIM_OUTPUT_DIR

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
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_recent_events(limit=50):
    events = []
    pattern = os.path.join(DATA_DIR, "cam_*", "events.jsonl")
    files = glob.glob(pattern)
    
    for ef in files:
        cam_id = os.path.basename(os.path.dirname(ef))
        try:
            with open(ef, "r") as f:
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
    if "spgs" in state:
        for spg in state["spgs"]:
            spg_id = spg.get("id")
            snap_path = find_spg_snapshot(spg_id)
            if snap_path:
                spg["snapshot_url"] = f"/api/snapshot/{spg_id}"
            else:
                spg["snapshot_url"] = None
    
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


async def mjpeg_generator(cam_id: str, request: Request):
    """Yields MJPEG stream from latest_frame.jpg. Stops when client disconnects."""
    import asyncio
    file_path = os.path.join(DATA_DIR, cam_id, "snapshots", "latest_frame.jpg")
    
    while not await request.is_disconnected():
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    frame_data = f.read()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                
                await asyncio.sleep(0.2)
            except Exception:
                await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(1.0)

@app.get("/stream/{cam_id}")
async def stream_feed(cam_id: str, request: Request):
    return StreamingResponse(
        mjpeg_generator(cam_id, request),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# Gallery Management

GALLERY_DIR = os.path.join(BASE_DIR, "data", "gallery")

_detector_instance: "FaceDetector | None" = None

def _get_detector():
    global _detector_instance
    if _detector_instance is None:
        cfg = load_settings()
        _detector_instance = FaceDetector(
            name=cfg.recognition.model_name,
            providers=cfg.recognition.execution_providers,
            det_size=tuple(cfg.recognition.det_size)
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
    store = GalleryStore(os.path.join(BASE_DIR, "data"))
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

        store = GalleryStore(os.path.join(BASE_DIR, "data"))
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
    uvicorn.run("src.frontend.main:app", host="0.0.0.0", port=8000, reload=True)
