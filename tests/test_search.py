import numpy as np
import pytest

from app import config, db, search


def _artwork(id_: str, movement: str = "Cubism") -> dict:
    return {"id": id_, "title": id_, "artist": "X", "year": 1900, "year_display": "1900", "movement": movement,
            "medium": "Oil", "image_url": "http://img", "source_url": "http://src", "source": "aic", "license": "CC0"}


def _seed(vectors: dict[str, list[float]]) -> None:
    with db.connect() as conn:
        for id_, vec in vectors.items():
            db.upsert_artwork(conn, _artwork(id_))
            db.save_embedding(conn, id_, np.array(vec, dtype="float32"), config.MODEL_EMBED)


def test_top_k_orders_by_cosine_and_ignores_vector_norm(tmp_db):
    # b est colinéaire à la requête mais 100x plus long : seul l'angle compte
    _seed({"a": [1, 0], "b": [100, 1], "c": [0, 1], "d": [-1, 0]})
    results = search.top_k(np.array([1.0, 0.0]), k=4)
    assert [m["id"] for m, _ in results] == ["a", "b", "c", "d"]
    scores = [s for _, s in results]
    assert scores[0] == pytest.approx(1.0, abs=1e-6)
    assert scores[1] == pytest.approx(1.0, abs=1e-3)
    assert scores[2] == pytest.approx(0.0, abs=1e-6)
    assert scores[3] == pytest.approx(-1.0, abs=1e-6)


def test_top_k_excludes_query_artwork_for_leave_one_out(tmp_db):
    _seed({"a": [1, 0], "b": [0.9, 0.1], "c": [0, 1]})
    results = search.top_k(np.array([1.0, 0.0]), k=3, exclude_id="a")
    assert [m["id"] for m, _ in results] == ["b", "c"]


def test_top_k_on_empty_corpus_returns_nothing(tmp_db):
    assert search.top_k(np.array([1.0, 0.0]), k=5) == []
