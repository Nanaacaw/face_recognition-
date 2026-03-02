import multiprocessing
import time
import numpy as np
import cv2  # type: ignore
import traceback
from typing import Any
from src.settings.logger import logger
from src.pipeline.face_detector import FaceDetector
from src.pipeline.matcher import Matcher
from src.storage.gallery_store import GalleryStore


class InferenceServer:
    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
        model_name: str,
        execution_providers: list,
        det_size: tuple,
        threshold: float,
        gallery_path: str,
        gallery_subdir: str = "gallery",
        shared_buffers: dict | None = None,
        frame_skip: int = 0,
        frame_skip_value: Any | None = None,
        min_det_score: float = 0.0,
        min_face_width_px: int = 0,
        min_det_score_value: Any | None = None,
        min_face_width_px_value: Any | None = None,
        roi_by_camera: dict[str, tuple[float, float, float, float] | None] | None = None,
    ):
        """
        Server process that consumes frames and produces inference results.
        
        Modes:
          - Queue Mode (legacy):  frame data arrives via input_queue tuple
          - Shared Memory Mode:   frame stored in shared_buffers[cam_id], 
                                  input_queue only carries metadata (cam_id, frame_id, timestamp)
        
        frame_skip: 0 = process every frame, N = skip N frames between inferences.
        """
        self.input_queue = input_queue
        self.output_queue = output_queue
        
        # Config
        self.model_name = model_name
        self.providers = execution_providers
        self.det_size = det_size
        self.threshold = threshold
        self.gallery_path = gallery_path
        self.gallery_subdir = gallery_subdir
        self.frame_skip = max(0, frame_skip)
        self.frame_skip_value = frame_skip_value
        self.min_det_score = max(0.0, float(min_det_score))
        self.min_face_width_px = max(0, int(min_face_width_px))
        self.min_det_score_value = min_det_score_value
        self.min_face_width_px_value = min_face_width_px_value
        self.roi_by_camera = roi_by_camera or {}
        
        # Shared Memory (optional)
        self._shared_buffer_configs = shared_buffers  # dict of cam_id -> (name, max_h, max_w, lock)
        self._buffers = {}  # Attached SharedFrameBuffer instances (created in run())
        
        # State (initialized in run())
        self.detector = None
        self.matcher = None
        
        # Frame skip counters per camera
        self._skip_counters: dict[str, int] = {}
        
    def run(self):
        """
        Main loop for the inference process. 
        MUST be called inside the new process target function.
        """
        pid = multiprocessing.current_process().pid
        logger.info(f"[InferenceServer] Starting up (PID={pid})...")
        
        try:
            # 1. Load Model (Heavy Operation - Done Once)
            logger.info(f"[InferenceServer] Loading model '{self.model_name}' on {self.providers}...")
            self.detector = FaceDetector(
                name=self.model_name,
                providers=self.providers,
                det_size=self.det_size
            )
            self.detector.start()
            
            # 2. Load Gallery
            logger.info(f"[InferenceServer] Loading gallery from {self.gallery_path}...")
            store = GalleryStore(self.gallery_path, gallery_subdir=self.gallery_subdir)
            gallery_data = store.load_all()
            
            self.matcher = Matcher(threshold=self.threshold)
            self.matcher.load_gallery(gallery_data)
            logger.info(
                "[InferenceServer] Ready! Gallery: %s people, frame_skip=%s, min_det_score=%.2f, min_face_width_px=%s",
                len(gallery_data),
                self.frame_skip,
                self.min_det_score,
                self.min_face_width_px,
            )
            roi_enabled = [cid for cid, roi in self.roi_by_camera.items() if roi is not None]
            logger.info(
                "[InferenceServer] ROI enabled for %s/%s camera(s).",
                len(roi_enabled),
                len(self.roi_by_camera),
            )
            
            # 3. Attach to Shared Memory Buffers (if configured)
            if self._shared_buffer_configs:
                from src.pipeline.shared_frame_buffer import SharedFrameBuffer
                for cam_id, (name, max_h, max_w, lock) in self._shared_buffer_configs.items():
                    self._buffers[cam_id] = SharedFrameBuffer.attach(name, max_h, max_w, lock)
                logger.info(f"[InferenceServer] Attached to {len(self._buffers)} shared memory buffers.")
            
            # 4. Processing Loop
            while True:
                try:
                    item = self.input_queue.get(timeout=1.0)
                    
                    if isinstance(item, str) and item == "STOP":
                        logger.info("[InferenceServer] Received STOP signal.")
                        break
                    
                    # Determine mode by tuple length.
                    # Shared Memory (new):   (camera_id, frame_id, capture_ts, enqueue_ts)
                    # Shared Memory (legacy):(camera_id, frame_id, capture_ts)
                    # Queue (new):           (camera_id, frame_id, frame_bgr, capture_ts, enqueue_ts)
                    # Queue (legacy):        (camera_id, frame_id, frame_bgr, capture_ts)
                    capture_ts = time.time()
                    enqueue_ts = capture_ts

                    if len(item) == 3:
                        camera_id, frame_id, capture_ts = item
                        enqueue_ts = capture_ts
                        frame_bgr = self._read_from_shared(camera_id)
                    elif len(item) == 4 and isinstance(item[2], (int, float)) and isinstance(item[3], (int, float)):
                        camera_id, frame_id, capture_ts, enqueue_ts = item
                        frame_bgr = self._read_from_shared(camera_id)
                    elif len(item) == 4:
                        camera_id, frame_id, frame_bgr, capture_ts = item
                        enqueue_ts = capture_ts
                    elif len(item) == 5:
                        camera_id, frame_id, frame_bgr, capture_ts, enqueue_ts = item
                    else:
                        logger.warning(f"[InferenceServer] Unsupported input tuple format len={len(item)}")
                        continue
                     
                    if frame_bgr is None:
                        continue

                    # --- FRAME SKIP ---
                    current_skip = self.frame_skip
                    if self.frame_skip_value is not None:
                        try:
                            current_skip = max(0, int(self.frame_skip_value.value))
                        except Exception:
                            current_skip = self.frame_skip

                    if current_skip > 0:
                        count = self._skip_counters.get(camera_id, 0)
                        if count < current_skip:
                            self._skip_counters[camera_id] = count + 1
                            continue
                        self._skip_counters[camera_id] = 0

                    # --- INFERENCE ---
                    t0 = time.time()
                    capture_to_inference_ms = max(0.0, (t0 - float(capture_ts)) * 1000.0)
                    input_queue_wait_ms = max(0.0, (t0 - float(enqueue_ts)) * 1000.0)

                    current_min_det_score = self.min_det_score
                    if self.min_det_score_value is not None:
                        try:
                            current_min_det_score = max(0.0, float(self.min_det_score_value.value))
                        except Exception:
                            current_min_det_score = self.min_det_score

                    current_min_face_width_px = self.min_face_width_px
                    if self.min_face_width_px_value is not None:
                        try:
                            current_min_face_width_px = max(0, int(self.min_face_width_px_value.value))
                        except Exception:
                            current_min_face_width_px = self.min_face_width_px
                     
                    roi_rect = self._resolve_roi_rect(camera_id, frame_bgr.shape)
                    roi_offset_x = 0.0
                    roi_offset_y = 0.0
                    frame_for_detection = frame_bgr
                    if roi_rect is not None:
                        rx1, ry1, rx2, ry2 = roi_rect
                        frame_for_detection = frame_bgr[ry1:ry2, rx1:rx2]
                        roi_offset_x = float(rx1)
                        roi_offset_y = float(ry1)

                    faces = self.detector.detect(frame_for_detection)
                    
                    results = []
                    for f in faces:
                        det_score = float(getattr(f, "det_score", 0.0))
                        bbox_f = np.asarray(f.bbox, dtype=np.float32)
                        x1f, y1f, x2f, y2f = [float(v) for v in bbox_f]
                        if roi_rect is not None:
                            x1f += roi_offset_x
                            y1f += roi_offset_y
                            x2f += roi_offset_x
                            y2f += roi_offset_y
                        face_width_px = max(0.0, x2f - x1f)
                        bbox = [int(x1f), int(y1f), int(x2f), int(y2f)]

                        if det_score < current_min_det_score:
                            continue
                        if face_width_px < current_min_face_width_px:
                            continue

                        emb = getattr(f, "embedding", None)
                        matched, spg_id, name, sim = self.matcher.match(emb)
                        
                        res = {
                            "bbox": bbox,
                            "det_score": det_score,
                            "face_width_px": round(face_width_px, 2),
                            "matched": matched,
                            "spg_id": spg_id,
                            "name": name,
                            "similarity": float(sim)
                        }
                        results.append(res)
                    
                    dur_ms = (time.time() - t0) * 1000
                    inference_done_ts = time.time()
                     
                    self.output_queue.put({
                        "camera_id": camera_id,
                        "frame_id": frame_id,
                        "timestamp": float(capture_ts),
                        "enqueue_ts": float(enqueue_ts),
                        "capture_to_inference_ms": capture_to_inference_ms,
                        "input_queue_wait_ms": input_queue_wait_ms,
                        "inference_done_ts": inference_done_ts,
                        "faces": results,
                        "inference_time_ms": dur_ms
                    })
                    
                except multiprocessing.queues.Empty:
                    continue
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"[InferenceServer] Error processing frame: {e}")
                    traceback.print_exc()
                    continue

        except Exception as e:
            logger.critical(f"[InferenceServer] CRASHED: {e}")
            traceback.print_exc()
        finally:
            # Cleanup shared memory attachments
            for buf in self._buffers.values():
                buf.close()
            logger.info("[InferenceServer] Stopped.")

    def _read_from_shared(self, camera_id: str) -> np.ndarray | None:
        """Read frame from shared memory buffer for given camera."""
        buf = self._buffers.get(camera_id)
        if buf is None:
            return None
        frame, _ = buf.read()
        return frame

    def _resolve_roi_rect(
        self,
        camera_id: str,
        frame_shape: tuple[int, ...],
    ) -> tuple[int, int, int, int] | None:
        roi = self.roi_by_camera.get(camera_id)
        if roi is None:
            return None

        try:
            x1, y1, x2, y2 = [float(v) for v in roi]
        except (TypeError, ValueError):
            return None

        h, w = frame_shape[:2]
        if w <= 0 or h <= 0:
            return None

        # Normalized ROI: [0..1]
        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.0:
            x1 *= w
            x2 *= w
            y1 *= h
            y2 *= h

        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        ix1 = max(0, min(w - 1, int(round(x1))))
        iy1 = max(0, min(h - 1, int(round(y1))))
        ix2 = max(1, min(w, int(round(x2))))
        iy2 = max(1, min(h, int(round(y2))))

        if (ix2 - ix1) < 16 or (iy2 - iy1) < 16:
            return None

        return (ix1, iy1, ix2, iy2)
