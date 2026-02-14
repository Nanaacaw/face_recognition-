import numpy as np


class Matcher:
    def __init__(self, threshold: float):
        self.threshold = float(threshold)
        self.gallery: dict[str, dict] = {}  # spg_id -> {name, embeddings(np.ndarray)}

    def load_gallery(self, gallery_payload: dict[str, dict]) -> None:
        """
        gallery_payload example:
        {
          "001": {"spg_id":"001","name":"Nana","embeddings":[[...],[...]]}
        }
        """
        self.gallery = {}

        for spg_id, person in gallery_payload.items():
            embs_list = person.get("embeddings", [])
            embs = np.asarray(embs_list, dtype=np.float32)

            if embs.ndim != 2 or embs.shape[0] == 0:
                continue

            # normalize embeddings
            norms = np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
            embs = embs / norms

            self.gallery[spg_id] = {
                "name": person.get("name", spg_id),
                "embeddings": embs,
            }

    def match(self, emb: np.ndarray | None):
        """
        Returns (matched: bool, spg_id: str|None, name: str|None, similarity: float)
        Uses cosine similarity (dot product because vectors normalized).
        """
        if emb is None or len(self.gallery) == 0:
            return (False, None, None, 0.0)

        emb = np.asarray(emb, dtype=np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-12)

        best_spg_id = None
        best_name = None
        best_sim = -1.0

        for spg_id, item in self.gallery.items():
            embs = item["embeddings"]  # (N, D)
            sims = embs @ emb          # (N,)
            sim = float(np.max(sims))
            if sim > best_sim:
                best_sim = sim
                best_spg_id = spg_id
                best_name = item["name"]

        matched = best_sim >= self.threshold
        if not matched:
            return (False, None, None, best_sim)

        return (True, best_spg_id, best_name, best_sim)
