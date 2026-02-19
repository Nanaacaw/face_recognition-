import time
import numpy as np
import cv2

from src.pipeline.face_detector import FaceDetector


def enroll_from_photos(
    images: list[np.ndarray],
    spg_id: str,
    name: str,
    detector: FaceDetector,
    min_det_score: float = 0.60,
    min_face_width_px: int = 80,
) -> dict:
    """
    Extract face embeddings from a list of images.

    Args:
        images: List of BGR numpy arrays (cv2 format)
        spg_id: SPG identifier
        name: Person name
        detector: Pre-initialized FaceDetector instance
        min_det_score: Minimum detection confidence
        min_face_width_px: Minimum face width in pixels

    Returns:
        dict with keys: spg_id, name, embeddings, meta, last_face_crop (np.ndarray | None)

    Raises:
        ValueError: If no valid faces found in any image
    """
    embeddings: list[list[float]] = []
    meta_samples: list[dict] = []
    last_face_crop: np.ndarray | None = None

    for i, img in enumerate(images):
        faces = detector.detect(img)

        # Pick the face with highest detection score
        best = None
        best_score = -1.0
        for f in faces:
            score = float(getattr(f, "det_score", 0.0))
            if score > best_score:
                best_score = score
                best = f

        if best is None:
            continue

        x1, y1, x2, y2 = [int(v) for v in best.bbox]
        w = x2 - x1

        if best_score < min_det_score or w < min_face_width_px:
            continue

        emb = getattr(best, "embedding", None)
        if emb is None:
            continue

        emb = np.asarray(emb, dtype=np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-12)

        embeddings.append(emb.tolist())
        meta_samples.append({
            "ts": time.time(),
            "det_score": best_score,
            "face_width_px": int(w),
            "source_index": i,
        })

        last_face_crop = img[max(0, y1):y2, max(0, x1):x2]

    if not embeddings:
        raise ValueError(
            f"No valid faces detected in {len(images)} image(s). "
            f"Ensure faces are clear, well-lit, and facing the camera."
        )

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

    return payload, last_face_crop
