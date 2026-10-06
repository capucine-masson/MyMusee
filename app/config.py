"""Configuration centrale : chemins, modèles Cohere, limites. La clé n'est jamais en dur."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Windows : forcer l'UTF-8 sur la console (accents, emojis dans les logs)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent  # racine du projet
APP_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", encoding="utf-8")

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "").strip()

# Modèles vérifiés sur https://docs.cohere.com/docs/models (surchargeables via .env)
MODEL_VISION = os.getenv("COHERE_MODEL_VISION", "command-a-vision-07-2025")
MODEL_CHAT = os.getenv("COHERE_MODEL_CHAT", "command-a-03-2025")
MODEL_EMBED = os.getenv("COHERE_MODEL_EMBED", "embed-v4.0")
MODEL_RERANK = os.getenv("COHERE_MODEL_RERANK", "rerank-v4.0-pro")

COHERE_TIMEOUT = 30  # secondes, appels Cohere
HTTP_TIMEOUT = 15  # secondes, appels HTTP externes (AIC, Wikidata, images)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 Mo
ALLOWED_MIME = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}
EMBED_IMAGE_WIDTH = 640  # même taille côté corpus et côté requête
VISION_MAX_SIDE = 1536

CANDIDATES_K = 20  # top-k avant rerank
FINAL_K = 5  # résultats affichés

DB_PATH = BASE_DIR / "data" / "musee.db"
ART_CACHE_DIR = BASE_DIR / "data" / "cache" / "art"  # images du corpus (domaine public) servies par /art/{id}
MAX_ART_BYTES = 8 * 1024 * 1024
USER_AGENT = "MuseeIA-demo/0.1 (projet portfolio; contact: masson.capucine@gmail.com)"

LEVELS = ("beginner", "enthusiast", "expert")
LANGS = ("fr", "en")
DEFAULT_LANG = "fr"
DEFAULT_LEVEL = "enthusiast"

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
