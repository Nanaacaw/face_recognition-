import time
import cv2
from pathlib import Path

class SnapshotStore:
    def __init__(self, data_dir: str):
        self.root = Path(data_dir) / "snapshots"
        self.root.mkdir(parents=True, exist_ok=True)

    def save_alert_frame(self, outlet_id: str, camera_id: str, frame) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_absent_{outlet_id}_{camera_id}.jpg".replace(" ", "_")
        path = self.root / filename
        cv2.imwrite(str(path), frame)
        return str(path)

    def save_latest_face(self, spg_id: str, frame) -> str:
        """Saves or overwrites the latest known face for an SPG."""
        filename = f"latest_{spg_id}.jpg"
        path = self.root / filename
        cv2.imwrite(str(path), frame)
        return str(path)
        