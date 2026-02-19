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
        Converts to parallel lists/arrays for vectorized search.
        """
        self.gallery = {}
        
        self.gallery_vectors = []
        self.gallery_meta = [] # list of (spg_id, name)

        for spg_id, person in gallery_payload.items():
            embs_list = person.get("embeddings", [])
            embs = np.asarray(embs_list, dtype=np.float32)

            if embs.ndim != 2 or embs.shape[0] == 0:
                continue

            # normalize embeddings
            norms = np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
            embs = embs / norms
            
            # Store in original dict structure (optional, kept for backward compat if needed)
            self.gallery[spg_id] = {
                "name": person.get("name", spg_id),
                "embeddings": embs,
            }

            for i in range(embs.shape[0]):
                self.gallery_vectors.append(embs[i])
                self.gallery_meta.append((spg_id, person.get("name", spg_id)))

        if self.gallery_vectors:
            self.matrix = np.stack(self.gallery_vectors) # (N, 512)
        else:
            self.matrix = np.zeros((0, 512), dtype=np.float32)

    def match(self, emb: np.ndarray | None):
        """
        Returns (matched: bool, spg_id: str|None, name: str|None, similarity: float)
        Uses vectorized cosine similarity.
        """
        if emb is None or self.matrix.shape[0] == 0:
            return (False, None, None, 0.0)

        emb = np.asarray(emb, dtype=np.float32)
        # normalize query
        emb = emb / (np.linalg.norm(emb) + 1e-12)

        # Vectorized dot product: (N, 512) @ (512,) -> (N,)
        sims = self.matrix @ emb
        
        best_idx = np.argmax(sims)
        best_sim = float(sims[best_idx])
        
        if best_sim < self.threshold:
            return (False, None, None, best_sim)

        spg_id, name = self.gallery_meta[best_idx]
        return (True, spg_id, name, best_sim)
