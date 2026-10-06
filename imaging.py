"""Validation et préparation des images, en mémoire uniquement (rien n'est écrit sur disque)."""
import base64
import io

from PIL import Image, UnidentifiedImageError

from config import ALLOWED_MIME, EMBED_IMAGE_WIDTH, MAX_UPLOAD_BYTES, VISION_MAX_SIDE
from i18n import AppError

Image.MAX_IMAGE_PIXELS = 60_000_000  # protège contre les « decompression bombs »


def validate_upload(raw: bytes, content_type: str | None, lang: str) -> Image.Image:
    """Contrôle taille, type déclaré ET contenu réel. Retourne une image RGB."""
    if not raw:
        raise AppError("empty_file", 400, lang)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AppError("too_large", 413, lang)
    if (content_type or "").lower() not in ALLOWED_MIME:
        raise AppError("bad_type", 415, lang)
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()  # détecte les fichiers tronqués / corrompus
        img = Image.open(io.BytesIO(raw))  # verify() invalide l'objet : on rouvre
        if (img.format or "").lower() not in set(ALLOWED_MIME.values()) | {"mpo"}:
            raise AppError("bad_type", 415, lang)
        return _flatten(img)
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise AppError("not_an_image", 400, lang)


def _flatten(img: Image.Image) -> Image.Image:
    """Aplati la transparence sur fond blanc et convertit en RGB."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def _to_data_url(img: Image.Image, quality: int = 88) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def for_vision(img: Image.Image) -> str:
    out = img.copy()
    out.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE), Image.LANCZOS)
    return _to_data_url(out, 90)


def for_embedding(img: Image.Image) -> str:
    """Même règle que le corpus : largeur max 640 px (aucun agrandissement)."""
    out = img.copy()
    if out.width > EMBED_IMAGE_WIDTH:
        ratio = EMBED_IMAGE_WIDTH / out.width
        out = out.resize((EMBED_IMAGE_WIDTH, max(1, round(out.height * ratio))), Image.LANCZOS)
    return _to_data_url(out, 88)


def bytes_to_embedding_data_url(raw: bytes) -> str:
    """Pour les images téléchargées du corpus (déjà redimensionnées côté source)."""
    img = Image.open(io.BytesIO(raw))
    return for_embedding(_flatten(img))
