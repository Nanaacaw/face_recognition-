from __future__ import annotations

import numpy as np
from insightface.app import FaceAnalysis

class FaceDetector:
    def __init__(self, name: str = "buffalo_s", providers: list[str] | None = None, det_size=(640,640)):
        self.det_size = det_size
        self.name = name
        self.providers = providers
        if self.providers is None:
             self.providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        
        self.app: FaceAnalysis | None = None

    def start(self) -> None:
        try:
             import onnxruntime as ort
             available = ort.get_available_providers()
             valid_providers = [p for p in self.providers if p in available]
             if not valid_providers:
                 print(f"[WARN] Requested providers {self.providers} not available. Found: {available}. Using CPU fallback.")
                 valid_providers = ['CPUExecutionProvider']
        except ImportError:
             valid_providers = ['CPUExecutionProvider']

        print(f"[FaceDetector] Loading model '{self.name}' with providers: {valid_providers}")
        self.app = FaceAnalysis(name=self.name, providers=valid_providers)
        self.app.prepare(ctx_id=0, det_size=self.det_size)

    def detect(self, frame_bgr: np.ndarray):
        """
        Return list of faces from InsightFace.
        Each face has: bbox, kps, det_score, embedding (embedding may be present)
        """
        if self.app is None:
             print("[ERR] FaceDetector not started!")
             return []
             
        return self.app.get(frame_bgr)
