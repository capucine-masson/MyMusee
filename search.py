"""Recherche vectorielle en mémoire : similarité cosinus avec numpy (choix assumé : ~300 vecteurs)."""
import threading

import numpy as np

import config
import db

_lock = threading.Lock()
_cache: dict = {"metas": None, "mat": None}


def load_index(force: bool = False) -> tuple[list[dict], np.ndarray]:
    with _lock:
        if force or _cache["metas"] is None:
            metas, mat = db.load_embedded_artworks(config.MODEL_EMBED)
            if len(mat):
                mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
            _cache["metas"], _cache["mat"] = metas, mat
        return _cache["metas"], _cache["mat"]


def top_k(query_vec: np.ndarray, k: int, exclude_id: str | None = None) -> list[tuple[dict, float]]:
    """Top-k par cosinus. `exclude_id` sert au leave-one-out de l'évaluation."""
    metas, mat = load_index()
    if not len(metas):
        return []
    q = np.asarray(query_vec, dtype="float32")
    q = q / (np.linalg.norm(q) + 1e-12)
    scores = mat @ q
    if exclude_id is not None:
        for i, m in enumerate(metas):
            if m["id"] == exclude_id:
                scores[i] = -np.inf
                break
    k = min(k, len(metas))
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(metas[i], float(scores[i])) for i in idx if np.isfinite(scores[i])]


def pca_2d() -> dict:
    """Projection 2D des embeddings par PCA (SVD numpy), pour la page /salle."""
    metas, mat = load_index()
    if len(metas) < 3:
        return {"points": [], "explained": [0, 0]}
    centered = mat - mat.mean(axis=0)
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T
    var = (s**2) / np.sum(s**2)
    # normalisation dans [-1, 1] pour un rendu SVG simple
    coords = coords / (np.abs(coords).max(axis=0) + 1e-12)
    points = [
        {
            "id": m["id"],
            "title": m["title"],
            "artist": m["artist"],
            "year": m["year_display"],
            "movement": m["movement"],
            "image_url": db.art_url(m["id"]),
            "source_url": m["source_url"],
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
        }
        for i, m in enumerate(metas)
    ]
    return {"points": points, "explained": [float(var[0]), float(var[1])]}
