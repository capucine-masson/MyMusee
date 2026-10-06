"""Accès SQLite direct (module sqlite3, requêtes paramétrées uniquement, pas d'ORM)."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np

from .config import DB_PATH, DEFAULT_LANG, DEFAULT_LEVEL, LANGS, LEVELS

SCHEMA = """
CREATE TABLE IF NOT EXISTS artworks (
    id              TEXT PRIMARY KEY,        -- ex. 'aic:28560' ou 'wd:Q123'
    title           TEXT NOT NULL,
    artist          TEXT,
    year            INTEGER,
    year_display    TEXT,
    movement        TEXT NOT NULL,
    medium          TEXT,
    image_url       TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    source          TEXT NOT NULL,           -- 'aic' | 'wikidata'
    license         TEXT,
    embedding       BLOB,                    -- float32, little-endian
    embedding_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_artworks_movement ON artworks(movement);

CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    lang        TEXT NOT NULL,
    level       TEXT NOT NULL,
    summary     TEXT,                        -- ex. « Impressionnisme · Claude Monet (?) »
    result_json TEXT NOT NULL                -- métadonnées + résultat, jamais l'image
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------- settings
def get_setting(key: str, default: str) -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_preferences() -> dict:
    lang = get_setting("lang", DEFAULT_LANG)
    level = get_setting("level", DEFAULT_LEVEL)
    return {
        "lang": lang if lang in LANGS else DEFAULT_LANG,
        "level": level if level in LEVELS else DEFAULT_LEVEL,
    }


# ----------------------------------------------------------------- history
def add_history(lang: str, level: str, summary: str, result: dict) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO history(created_at, lang, level, summary, result_json) VALUES(?,?,?,?,?)",
            (now, lang, level, summary, json.dumps(result, ensure_ascii=False)),
        )
        return cur.lastrowid


def update_history(history_id: int, result: dict) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE history SET result_json = ? WHERE id = ?",
            (json.dumps(result, ensure_ascii=False), history_id),
        )


def list_history(limit: int = 10) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, lang, level, summary FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(history_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, created_at, lang, level, summary, result_json FROM history WHERE id = ?",
            (history_id,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["result"] = json.loads(out.pop("result_json"))
    return out


def clear_history() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM history")


# ---------------------------------------------------------------- artworks
ARTWORK_PUBLIC_COLS = (
    "id, title, artist, year, year_display, movement, medium, image_url, source_url, source, license"
)


def upsert_artwork(conn: sqlite3.Connection, a: dict) -> None:
    """Insère ou met à jour les métadonnées SANS écraser un embedding déjà calculé."""
    conn.execute(
        """
        INSERT INTO artworks(id, title, artist, year, year_display, movement, medium,
                             image_url, source_url, source, license)
        VALUES(:id, :title, :artist, :year, :year_display, :movement, :medium,
               :image_url, :source_url, :source, :license)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title, artist = excluded.artist, year = excluded.year,
            year_display = excluded.year_display, movement = excluded.movement,
            medium = excluded.medium, image_url = excluded.image_url,
            source_url = excluded.source_url, license = excluded.license
        """,
        a,
    )


def save_embedding(conn: sqlite3.Connection, artwork_id: str, vec: np.ndarray, model: str) -> None:
    conn.execute(
        "UPDATE artworks SET embedding = ?, embedding_model = ? WHERE id = ?",
        (np.asarray(vec, dtype="<f4").tobytes(), model, artwork_id),
    )


def artworks_to_embed(model: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {ARTWORK_PUBLIC_COLS} FROM artworks "
            "WHERE embedding IS NULL OR embedding_model IS NOT ?",
            (model,),
        ).fetchall()
    return [dict(r) for r in rows]


def load_embedded_artworks(model: str) -> tuple[list[dict], np.ndarray]:
    """Retourne (métadonnées, matrice float32 [n, d]) des œuvres déjà vectorisées."""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {ARTWORK_PUBLIC_COLS}, embedding FROM artworks "
            "WHERE embedding IS NOT NULL AND embedding_model = ? ORDER BY id",
            (model,),
        ).fetchall()
    metas, vecs = [], []
    for r in rows:
        d = dict(r)
        vecs.append(np.frombuffer(d.pop("embedding"), dtype="<f4"))
        metas.append(d)
    if not vecs:
        return [], np.zeros((0, 0), dtype="float32")
    return metas, np.vstack(vecs).astype("float32")


def art_url(artwork_id: str) -> str:
    """URL locale servie par le proxy d'images (le navigateur ne contacte jamais AIC/Wikimedia)."""
    return f"/art/{artwork_id}"


def get_artwork_source_image(artwork_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT image_url FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    return row["image_url"] if row else None


def corpus_stats() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM artworks").fetchone()[0]
        embedded = conn.execute(
            "SELECT COUNT(*) FROM artworks WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        per = conn.execute(
            "SELECT movement, COUNT(*) AS n FROM artworks GROUP BY movement ORDER BY n DESC"
        ).fetchall()
    return {"total": total, "embedded": embedded, "movements": {r["movement"]: r["n"] for r in per}}


if __name__ == "__main__":
    init_db()
    print("Base initialisée :", DB_PATH)
