"""
MJPEG Streaming Server for Dashboard Live Camera Preview.
Reads latest_frame.jpg from each camera folder and serves as MJPEG stream.

Usage:
    python -m src.dashboard.stream_server
    
Endpoints:
    GET /stream/<camera_id>  → MJPEG stream (e.g. /stream/cam_01)
    GET /snapshot/<camera_id> → Single JPEG snapshot
    GET /cameras              → JSON list of available cameras
"""
import os
import time
import glob
from flask import Flask, Response, jsonify
from src.settings.settings import load_settings

app = Flask(__name__)

# Resolve data directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "sim_output")


def get_frame_path(camera_id: str) -> str:
    return os.path.join(DEFAULT_DATA_DIR, camera_id, "snapshots", "latest_frame.jpg")


def generate_mjpeg(camera_id: str):
    """Generator that yields MJPEG frames from latest_frame.jpg."""
    frame_path = get_frame_path(camera_id)
    last_mtime = 0
    last_data = None
    
    while True:
        try:
            if os.path.exists(frame_path):
                mtime = os.path.getmtime(frame_path)
                # Only re-read if file changed
                if mtime != last_mtime:
                    with open(frame_path, 'rb') as f:
                        last_data = f.read()
                    last_mtime = mtime
                
                if last_data:
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + last_data + b'\r\n'
                    )
        except (PermissionError, FileNotFoundError):
            pass  # File might be mid-write, skip this tick
        
        time.sleep(0.3)  # ~3 FPS


@app.route('/stream/<camera_id>')
def video_stream(camera_id):
    """MJPEG stream for a specific camera."""
    return Response(
        generate_mjpeg(camera_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/snapshot/<camera_id>')
def snapshot(camera_id):
    """Single JPEG snapshot for a specific camera."""
    frame_path = get_frame_path(camera_id)
    if os.path.exists(frame_path):
        with open(frame_path, 'rb') as f:
            data = f.read()
        return Response(data, mimetype='image/jpeg')
    return Response("No frame available", status=404)


@app.route('/cameras')
def list_cameras():
    """List all cameras with available frames."""
    pattern = os.path.join(DEFAULT_DATA_DIR, "cam_*", "snapshots", "latest_frame.jpg")
    frames = glob.glob(pattern)
    cameras = []
    for fp in sorted(frames):
        parts = fp.replace('\\', '/').split('/')
        # Find cam_XX in path
        for part in parts:
            if part.startswith("cam_"):
                cameras.append({
                    "id": part,
                    "stream_url": f"/stream/{part}",
                    "snapshot_url": f"/snapshot/{part}",
                })
                break
    return jsonify(cameras)


@app.route('/')
def index():
    """Simple HTML page showing all camera streams."""
    pattern = os.path.join(DEFAULT_DATA_DIR, "cam_*", "snapshots", "latest_frame.jpg")
    frames = sorted(glob.glob(pattern))
    
    cam_ids = []
    for fp in frames:
        parts = fp.replace('\\', '/').split('/')
        for part in parts:
            if part.startswith("cam_"):
                cam_ids.append(part)
                break
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Camera Streams</title>
        <style>
            body { background: #0a0a1a; color: white; font-family: 'Segoe UI', sans-serif; padding: 20px; }
            h1 { text-align: center; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px; }
            .cam-card { 
                background: #1a1a2e; border-radius: 12px; overflow: hidden; 
                border: 1px solid rgba(255,255,255,0.1); 
            }
            .cam-card img { width: 100%; display: block; }
            .cam-label { padding: 8px 16px; font-weight: 600; font-size: 0.9rem; }
        </style>
    </head>
    <body>
        <h1>📹 Live Camera Feeds</h1>
        <div class="grid">
    """
    
    for cam_id in cam_ids:
        html += f"""
            <div class="cam-card">
                <img src="/stream/{cam_id}" alt="{cam_id}">
                <div class="cam-label">📷 {cam_id.upper().replace('_', ' ')}</div>
            </div>
        """
    
    html += """
        </div>
    </body>
    </html>
    """
    return html


if __name__ == '__main__':
    print("=" * 50)
    print("📹 MJPEG Stream Server")
    print(f"   Data: {DEFAULT_DATA_DIR}")
    print(f"   URL:  http://localhost:8081")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8081, threaded=True)
