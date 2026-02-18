from __future__ import annotations

import numpy as np
from insightface.app import FaceAnalysis

class FaceDetector:
    def __init__(self, det_size=(640,640)):
        self.det_size = det_size
        self.app: FaceAnalysis | None = None

    def start(self) -> None:
        # ctx_id=0 means GPU (CUDA), ctx_id=-1 means CPU
        # InsightFace auto-selects providers based on installed packages
        self.app = FaceAnalysis(name="buffalo_l", providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        self.app.prepare(ctx_id=0, det_size=self.det_size)

    def detect(self, frame_bgr: np.ndarray):
        """
        Return list of faces from InsightFace.
        Each face has: bbox, kps, det_score, embedding (embedding may be present)
        """
        assert self.app is not None
        return self.app.get(frame_bgr)
