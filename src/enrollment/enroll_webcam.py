import time
import numpy as np
import cv2

from src.pipeline.webcam_reader import WebcamReader
from src.pipeline.face_detector import FaceDetector
from src.storage.gallery_store import GalleryStore

def enroll_from_webcam(
    spg_id: str,
    name: str,
    data_dir: str,
    webcam_index: int,
    process_fps: int,
    samples: int = 30,
    min_det_score: float = 0.60,
    min_face_width_px: int = 100,
    model_name: str = "buffalo_s",
    execution_providers: list[str] | None = None,
    det_size: tuple[int, int] = (640, 640),
):
    reader = WebcamReader(webcam_index, process_fps)
    detector = FaceDetector(
        name=model_name,
        providers=execution_providers,
        det_size=det_size
    )
    store = GalleryStore(data_dir)

    detector.start()
    reader.start()

    embeddings: list[list[float]] = []
    meta_samples: list[dict] = []

    last_face_crop = None

    print(f"[ENROLL] spg_id={spg_id} name={name}")
    print(f"[ENROLL] Target samples: {samples}")
    print("Press 'q' to abort.")

    try:
        while len(embeddings) < samples:
            frame = reader.read_throttled()
            if frame is None:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    raise KeyboardInterrupt()
                continue

            faces = detector.detect(frame)

            best = None
            best_score = -1.0

            for f in faces:
                score = float(getattr(f, "det_score", 0.0))
                if score > best_score:
                    best_score = score
                    best = f

            disp = frame.copy()

            if best is not None:
                x1, y1, x2, y2 = [int(v) for v in best.bbox]
                w = x2 - x1

                cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 255, 0), 2)

                cv2.putText(
                    disp,
                    f"score={best_score:.2f} w={w}px  {len(embeddings)}/{samples}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )

                if best_score >= min_det_score and w >= min_face_width_px:
                    emb = getattr(best, "embedding", None)

                    if emb is not None:
                        emb = np.asarray(emb, dtype=np.float32)
                        emb = emb / (np.linalg.norm(emb) + 1e-12)

                        embeddings.append(emb.tolist())

                        meta_samples.append(
                            {
                                "ts": time.time(),
                                "det_score": best_score,
                                "face_width_px": int(w),
                            }
                        )

                        # Save last face crop
                        last_face_crop = frame[y1:y2, x1:x2]

            else:
                cv2.putText(
                    disp,
                    f"no face  {len(embeddings)}/{samples}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )

            cv2.imshow("face_recog | enroll", disp)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                raise KeyboardInterrupt()

        payload = {
            "spg_id": spg_id,
            "name": name,
            "embeddings": embeddings,
            "meta": {
                "created_at": time.time(),
                "num_samples": len(embeddings),
                "min_det_score": min_det_score,
                "min_face_width_px": min_face_width_px,
                "samples": meta_samples,
            },
        }

        json_path = store.save_person(spg_id, payload)

        face_path = None
        if last_face_crop is not None:
            face_path = store.save_face_crop(spg_id, last_face_crop)

        print(f"[ENROLL] Saved embeddings: {json_path}")
        if face_path:
            print(f"[ENROLL] Saved last face crop: {face_path}")

    finally:
        reader.stop()
