"""Messages côté serveur (erreurs, libellés envoyés au modèle). L'UI a son propre dictionnaire JS."""
from .config import DEFAULT_LANG, LANGS

MESSAGES = {
    "fr": {
        "no_key": "Aucune clé Cohere n'est configurée. Ajoutez COHERE_API_KEY dans le fichier .env puis relancez l'application.",
        "bad_key": "La clé Cohere est refusée (401/403). Vérifiez COHERE_API_KEY dans .env.",
        "quota": "Le quota Cohere est dépassé (trop de requêtes). Patientez environ une minute puis réessayez.",
        "cohere_down": "Le service Cohere ne répond pas pour le moment. Réessayez dans quelques instants.",
        "cohere_error": "Cohere a refusé la requête. Réessayez avec une autre image.",
        "bad_type": "Format non pris en charge. Envoyez une image JPEG, PNG ou WebP.",
        "too_large": "Image trop lourde : 5 Mo maximum.",
        "empty_file": "Le fichier envoyé est vide.",
        "not_an_image": "Ce fichier n'est pas une image valide.",
        "not_painting": "Cette image ne semble pas être un tableau (photo, capture d'écran, document…). Essayez avec la photo d'une peinture.",
        "bad_model_output": "Le modèle a renvoyé une réponse inexploitable. Réessayez.",
        "corpus_empty": "Le corpus est vide. Lancez d'abord : python -m scripts.build_corpus",
        "not_found": "Élément introuvable.",
        "bad_request": "Requête invalide.",
        "internal": "Une erreur inattendue s'est produite. Réessayez.",
        "no_similar": "Aucune œuvre proche n'a pu être calculée.",
    },
    "en": {
        "no_key": "No Cohere key is configured. Add COHERE_API_KEY to the .env file and restart the app.",
        "bad_key": "The Cohere key was rejected (401/403). Check COHERE_API_KEY in .env.",
        "quota": "Cohere quota exceeded (too many requests). Wait about a minute and try again.",
        "cohere_down": "The Cohere service is not responding right now. Please try again shortly.",
        "cohere_error": "Cohere rejected the request. Try again with another image.",
        "bad_type": "Unsupported format. Please upload a JPEG, PNG or WebP image.",
        "too_large": "Image too large: 5 MB maximum.",
        "empty_file": "The uploaded file is empty.",
        "not_an_image": "This file is not a valid image.",
        "not_painting": "This image does not look like a painting (photo, screenshot, document…). Try a photo of a painting.",
        "bad_model_output": "The model returned an unusable answer. Please try again.",
        "corpus_empty": "The corpus is empty. First run: python -m scripts.build_corpus",
        "not_found": "Not found.",
        "bad_request": "Invalid request.",
        "internal": "An unexpected error occurred. Please try again.",
        "no_similar": "No similar artwork could be computed.",
    },
}

LANG_NAMES = {"fr": "French", "en": "English"}
LEVEL_GUIDE = {
    "beginner": "Audience: complete beginner. Short sentences, no jargon (define any art term in a few words), friendly tone, 3-5 sentences.",
    "enthusiast": "Audience: art enthusiast. Use proper art-history vocabulary with brief context, 5-8 sentences.",
    "expert": "Audience: art-history expert. Precise terminology (brushwork, composition, iconography, historiography), nuance and caveats, 6-10 sentences.",
}


def norm_lang(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


def t(lang: str | None, key: str) -> str:
    return MESSAGES[norm_lang(lang)].get(key) or MESSAGES[DEFAULT_LANG].get(key, key)


class AppError(Exception):
    """Erreur « propre » : un code stable, un statut HTTP, un message déjà localisé."""

    def __init__(self, key: str, status: int = 400, lang: str | None = None):
        self.key = key
        self.status = status
        self.message = t(lang, key)
        super().__init__(self.message)
