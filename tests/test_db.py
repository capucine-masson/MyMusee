import numpy as np

from app import config, db


def _artwork(**over) -> dict:
    base = {"id": "aic:1", "title": "Water Lilies", "artist": "Claude Monet", "year": 1906, "year_display": "1906",
            "movement": "Impressionism", "medium": "Oil on canvas", "image_url": "http://img", "source_url": "http://src",
            "source": "aic", "license": "CC0"}
    return base | over


def test_upsert_keeps_existing_embedding(tmp_db):
    with db.connect() as conn:
        db.upsert_artwork(conn, _artwork())
        db.save_embedding(conn, "aic:1", np.array([0.5, 0.25], dtype="float32"), config.MODEL_EMBED)
        db.upsert_artwork(conn, _artwork(title="Nymphéas"))  # mise à jour des métadonnées seulement
    metas, mat = db.load_embedded_artworks(config.MODEL_EMBED)
    assert metas[0]["title"] == "Nymphéas"
    assert mat.tolist() == [[0.5, 0.25]]


def test_embeddings_of_another_model_are_not_mixed(tmp_db):
    with db.connect() as conn:
        db.upsert_artwork(conn, _artwork())
        db.save_embedding(conn, "aic:1", np.array([1.0, 0.0], dtype="float32"), "old-model")
    assert db.load_embedded_artworks(config.MODEL_EMBED)[0] == []
    assert [a["id"] for a in db.artworks_to_embed(config.MODEL_EMBED)] == ["aic:1"]  # à ré-embarquer


def test_queries_are_parameterized(tmp_db):
    """Un identifiant malveillant est traité comme une valeur, jamais comme du SQL."""
    with db.connect() as conn:
        db.upsert_artwork(conn, _artwork())
    assert db.get_artwork_source_image("aic:1' OR '1'='1") is None
    assert db.get_artwork_source_image("aic:1") == "http://img"
    assert db.corpus_stats()["total"] == 1


def test_history_roundtrip_stores_result_only(tmp_db):
    hid = db.add_history("fr", "beginner", "Impressionnisme", {"movement": "Impressionism"})
    assert db.get_history(hid)["result"] == {"movement": "Impressionism"}
    assert [h["id"] for h in db.list_history()] == [hid]
    db.clear_history()
    assert db.list_history() == []


def test_invalid_preferences_fall_back_to_defaults(tmp_db):
    db.set_setting("lang", "klingon")
    assert db.get_preferences()["lang"] == config.DEFAULT_LANG
