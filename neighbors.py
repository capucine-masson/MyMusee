"""Test isolé de la recherche : image locale -> 5 plus proches voisins avec leur score cosinus.

Usage : python neighbors.py chemin\\vers\\image.jpg [-k 5]
"""
import argparse
from pathlib import Path

import cohere_svc
import config
import imaging
import search
from i18n import AppError


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    if not args.image.is_file():
        raise SystemExit(f"ECHEC : fichier introuvable : {args.image}")
    raw = args.image.read_bytes()
    suffix = args.image.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    try:
        img = imaging.validate_upload(raw, mime, "fr")
        vec, meta = cohere_svc.embed_images([imaging.for_embedding(img)], "fr")
    except AppError as e:
        raise SystemExit(f"ECHEC : {e.message}")

    results = search.top_k(vec[0], args.k)
    if not results:
        raise SystemExit("Corpus vide : lancez d'abord python build_corpus.py")
    print(f"Embedding : {meta['model']} en {meta['ms']} ms · corpus : {len(search.load_index()[0])} œuvres\n")
    for rank, (a, score) in enumerate(results, 1):
        print(f"{rank}. {score:.4f}  {a['title']} — {a['artist']} ({a['year_display']}) [{a['movement']}]")
        print(f"            {a['source_url']}")


if __name__ == "__main__":
    main()
