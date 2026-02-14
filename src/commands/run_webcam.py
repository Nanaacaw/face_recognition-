import cv2
import numpy as np

from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector
from src.storage.gallery_store import GalleryStore
from src.pipeline.matcher import Matcher


def run_webcam_recognition(
    data_dir: str,
    webcam_index: int,
    process_fps: int,
    threshold: float,
):
    store = GalleryStore(data_dir)
    gallery = store.load_all()

    matcher = Matcher(threshold=threshold)
    matcher.load_gallery(gallery)

    reader = WebcamReader(webcam_index, process_fps)
    detector = FaceDetector(det_size=(640, 640))

    detector.start()
    reader.start()

    print("[RUN] Webcam recognition started. Press 'q' to quit.")
    print(f"[RUN] Gallery loaded: {list(gallery.keys())}  threshold={threshold}")

    try:
        while True:
            frame = reader.read_throttled()

            if frame is not None:
                faces = detector.detect(frame)

                # pick best face (highest det_score)
                best = None
                best_score = -1.0
                for f in faces:
                    score = float(getattr(f, "det_score", 0.0))
                    if score > best_score:
                        best_score = score
                        best = f

                if best is not None:
                    x1, y1, x2, y2 = [int(v) for v in best.bbox]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    emb = getattr(best, "embedding", None)
                    matched, spg_id, name, sim = matcher.match(emb)

                    label = f"{name} ({sim:.2f})" if matched else f"UNKNOWN ({sim:.2f})"
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(0, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0) if matched else (0, 0, 255),
                        2,
                    )

                    cv2.putText(
                        frame,
                        f"det={best_score:.2f}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )

                cv2.imshow("face_recog | run", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    finally:
        reader.stop()
