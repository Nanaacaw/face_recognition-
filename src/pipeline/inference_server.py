import multiprocessing
import time
import numpy as np
import cv2  # type: ignore
import traceback
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
        shared_buffers: dict | None = None,
        frame_skip: int = 0,
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
        self.frame_skip = max(0, frame_skip)
        
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
            store = GalleryStore(self.gallery_path)
            gallery_data = store.load_all()
            
            self.matcher = Matcher(threshold=self.threshold)
            self.matcher.load_gallery(gallery_data)
            logger.info(f"[InferenceServer] Ready! Gallery: {len(gallery_data)} people, frame_skip={self.frame_skip}")
            
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
                    
                    # Determine mode by tuple length
                    if len(item) == 3:
                        # Shared Memory Mode: (camera_id, frame_id, timestamp)
                        camera_id, frame_id, ts = item
                        frame_bgr = self._read_from_shared(camera_id)
                    else:
                        # Queue Mode (legacy): (camera_id, frame_id, frame_bgr, timestamp)
                        camera_id, frame_id, frame_bgr, ts = item
                    
                    if frame_bgr is None:
                        continue

                    # --- FRAME SKIP ---
                    if self.frame_skip > 0:
                        count = self._skip_counters.get(camera_id, 0)
                        if count < self.frame_skip:
                            self._skip_counters[camera_id] = count + 1
                            continue
                        self._skip_counters[camera_id] = 0

                    # --- INFERENCE ---
                    t0 = time.time()
                    
                    faces = self.detector.detect(frame_bgr)
                    
                    results = []
                    for f in faces:
                        emb = getattr(f, "embedding", None)
                        matched, spg_id, name, sim = self.matcher.match(emb)
                        
                        res = {
                            "bbox": f.bbox.astype(int).tolist(),
                            "matched": matched,
                            "spg_id": spg_id,
                            "name": name,
                            "similarity": float(sim)
                        }
                        results.append(res)
                    
                    dur_ms = (time.time() - t0) * 1000
                    
                    self.output_queue.put({
                        "camera_id": camera_id,
                        "frame_id": frame_id,
                        "timestamp": ts,
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
