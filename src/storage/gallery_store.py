import json
from pathlib import Path
from typing import Any
import cv2
import numpy as np


class GalleryStore:
    def __init__(self, data_dir: str):
        self.root = Path(data_dir) / "gallery"
        self.root.mkdir(parents=True, exist_ok=True)

    def save_person(self, spg_id: str, payload: dict[str, Any]) -> Path:
        path = self.root / f"{spg_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def save_face_crop(self, spg_id:str, face_img: np.ndarray) -> Path:
        path = self.root / f"{spg_id}_last_face.jpg"
        cv2.imwrite(str(path), face_img)
        return path

    def load_all(self) -> dict[str, dict]:
        """
        Load all enrolled persons from data/gallery/*.json
        Returns dict keyed by spg_id.
        """
        out: dict[str, dict] = {}
        for p in self.root.glob("*.json"):
            with open(p, "r", encoding="utf-8") as f:
                out[p.stem] = json.load(f)
        return out