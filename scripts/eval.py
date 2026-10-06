"""Évaluation leave-one-out du moteur de similarité.

Pour chaque œuvre du corpus : on la retire, on retrouve ses voisins, et on mesure la proportion de voisins du
MÊME MOUVEMENT parmi les 5 premiers (precision@5).

Méthodes comparées
  1. embeddings seuls          : top 5 par cosinus (Embed) — corpus entier, sans appel API.
  2. embeddings + rerank       : top 20 par cosinus, puis Rerank, puis top 5 (échantillon, appels API).

Deux garde-fous méthodologiques
  * « hors même artiste » : on retire aussi les œuvres du même artiste, sinon on mesure surtout
    « retrouver un autre tableau du même peintre » (facile) et non la proximité de style.
  * le rerank est évalué en deux variantes : « aveugle » (les documents ne contiennent pas le mouvement,
    sinon l'étiquette fuite dans la requête) et « avec mouvement » (ce que fait réellement l'application).

La requête du rerank est la description produite par Command A Vision à partir de l'image de l'œuvre
(exactement comme dans l'application) ; les descriptions sont mises en cache (data/cache/descriptions.json).
Option --query-mode meta : requête construite sans appel vision à partir du titre/médium (plus faible, gratuit).

Usage
  python -m scripts.eval                        # embeddings (corpus entier) + rerank sur ~60 œuvres
  python -m scripts.eval --sample 100
  python -m scripts.eval --no-rerank            # embeddings seuls, zéro appel API
  python -m scripts.eval --query-mode meta
"""
import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict

import numpy as np

from scripts import build_corpus
from app import cohere_svc
from app import config
from app import search
from app.i18n import AppError

K = 5
CANDIDATES = config.CANDIDATES_K
DESC_CACHE = config.BASE_DIR / "data" / "cache" / "descriptions.json"
RESULTS_PATH = config.BASE_DIR / "data" / "eval_results.json"


def same_artist(a: dict, b: dict) -> bool:
    return bool(a["artist"]) and a["artist"] == b["artist"]


def ranking(i: int, metas: list[dict], mat: np.ndarray, exclude_same_artist: bool) -> list[int]:
    scores = mat @ mat[i]
    scores[i] = -np.inf
    if exclude_same_artist:
        for j, m in enumerate(metas):
            if j != i and same_artist(m, metas[i]):
                scores[j] = -np.inf
    order = np.argsort(-scores)
    return [int(j) for j in order if np.isfinite(scores[j])]


def precision(i: int, picked: list[int], metas: list[dict]) -> float:
    if not picked:
        return 0.0
    return sum(metas[j]["movement"] == metas[i]["movement"] for j in picked) / len(picked)


def stratified_sample(metas: list[dict], n: int, seed: int = 0) -> list[int]:
    rng = random.Random(seed)
    by_mov: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(metas):
        by_mov[m["movement"]].append(i)
    chosen: list[int] = []
    for mov, idx in sorted(by_mov.items()):
        take = min(len(idx), max(2, round(n * len(idx) / len(metas))))
        chosen += rng.sample(idx, take)
    return sorted(chosen)


# ----------------------------------------------------------- requêtes rerank
def load_cache() -> dict:
    if DESC_CACHE.exists():
        return json.loads(DESC_CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    DESC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DESC_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def vision_description(meta: dict, cache: dict, http) -> str | None:
    key = f"{meta['id']}|{config.MODEL_VISION}"
    if key in cache:
        return cache[key]
    data_url = build_corpus.download_embedding_image(http, {**meta, "title": meta["title"]})
    if not data_url:
        return None
    analysis, _ = cohere_svc.analyze_image(data_url, "enthusiast", "en", patient=True)
    cache[key] = analysis["search_description_en"]
    save_cache(cache)
    return cache[key]


def meta_query(meta: dict) -> str:
    """Requête gratuite sans mouvement ni artiste : très pauvre, sert de plancher."""
    return f"{meta['title']}. {meta.get('medium') or ''}. {meta.get('year_display') or ''}".strip()


def doc_text(meta: dict, with_movement: bool) -> str:
    text = cohere_svc.artwork_to_text(meta)
    return text if with_movement else ". ".join(p for p in text.split(". ") if not p.startswith("Movement:"))


def rerank_top(query: str, cands: list[dict], with_movement: bool) -> list[int]:
    client = cohere_svc.get_client()
    docs = [doc_text(c, with_movement) for c in cands]
    resp = cohere_svc._call(
        lambda: client.rerank(model=config.MODEL_RERANK, query=query, documents=docs, top_n=K), "fr", True
    )
    return [r.index for r in resp.results]


# ------------------------------------------------------------------- rapport
def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=60, help="taille de l'échantillon pour le rerank")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--query-mode", choices=["vision", "meta"], default="vision")
    ap.add_argument("--pause", type=float, default=0.0, help="pause (s) entre deux requêtes rerank")
    args = ap.parse_args()

    metas, mat = search.load_index(force=True)
    n = len(metas)
    if n < 20:
        raise SystemExit("Corpus trop petit ou non vectorisé : lancez d'abord python -m scripts.build_corpus")
    counts = defaultdict(int)
    for m in metas:
        counts[m["movement"]] += 1
    baseline = mean([(counts[m["movement"]] - 1) / (n - 1) for m in metas])
    print(f"Corpus : {n} œuvres, {len(counts)} mouvements · modèle d'embedding : {config.MODEL_EMBED}")
    print(f"Référence aléatoire (tirage au hasard) : precision@{K} ≈ {baseline:.3f}\n")

    result: dict = {"n": n, "movements": dict(counts), "k": K, "random_baseline": baseline,
                    "embed_model": config.MODEL_EMBED, "rerank_model": config.MODEL_RERANK,
                    "query_mode": args.query_mode}

    # 1) embeddings seuls, corpus entier (gratuit)
    emb = {"all": [], "cross": []}
    per_mov = defaultdict(lambda: {"emb": [], "emb_x": [], "rr_blind": [], "rr_lab": []})
    for i in range(n):
        for key, excl in (("all", False), ("cross", True)):
            p = precision(i, ranking(i, metas, mat, excl)[:K], metas)
            emb[key].append(p)
            per_mov[metas[i]["movement"]]["emb" if key == "all" else "emb_x"].append(p)
    result["embeddings_full"] = {"precision": mean(emb["all"]), "precision_cross_artist": mean(emb["cross"])}

    rows = [
        ("Aléatoire", baseline, baseline, n),
        ("Embeddings seuls (corpus entier)", mean(emb["all"]), mean(emb["cross"]), n),
    ]

    # 2) rerank sur un échantillon
    if not args.no_rerank:
        sample = stratified_sample(metas, args.sample)
        print(f"Rerank : {len(sample)} œuvres, requête = {args.query_mode}, "
              f"{config.MODEL_RERANK} (variantes aveugle / avec mouvement × même artiste inclus / exclu)\n")
        cache = load_cache()
        acc = defaultdict(list)
        t0 = time.time()
        try:
            with build_corpus.http_client() as http:
                for step, i in enumerate(sample, 1):
                    m = metas[i]
                    q = vision_description(m, cache, http) if args.query_mode == "vision" else meta_query(m)
                    if not q:
                        continue
                    for tag, excl in (("", False), ("_x", True)):
                        cand_idx = ranking(i, metas, mat, excl)[:CANDIDATES]
                        cands = [metas[j] for j in cand_idx]
                        acc["emb" + tag].append(precision(i, cand_idx[:K], metas))
                        for name, lab in (("rr_blind", False), ("rr_lab", True)):
                            order = rerank_top(q, cands, lab)
                            p = precision(i, [cand_idx[o] for o in order], metas)
                            acc[name + tag].append(p)
                            if tag == "":
                                per_mov[m["movement"]][name].append(p)
                            if args.pause:
                                time.sleep(args.pause)
                    if step % 10 == 0 or step == len(sample):
                        print(f"  {step}/{len(sample)}  ({time.time() - t0:.0f} s)", flush=True)
        except AppError as e:
            print(f"\nArrêt anticipé : {e.message}\nRésultats partiels ci-dessous (relancez : le cache évite de refaire les appels vision).")

        k = len(acc["emb"])
        if k:
            rows += [
                (f"Embeddings seuls (échantillon de {k})", mean(acc["emb"]), mean(acc["emb_x"]), k),
                ("Embeddings + rerank, aveugle (sans mouvement)", mean(acc["rr_blind"]), mean(acc["rr_blind_x"]), k),
                ("Embeddings + rerank, avec mouvement (application)", mean(acc["rr_lab"]), mean(acc["rr_lab_x"]), k),
            ]
            result["rerank_sample"] = {name: mean(v) for name, v in acc.items()} | {"n": k}

    w = max(len(r[0]) for r in rows)
    print("\n" + "Méthode".ljust(w) + f" | precision@{K} | hors même artiste |   n")
    print("-" * w + "-+-------------+------------------+-----")
    for name, a, b, nn in rows:
        print(f"{name.ljust(w)} | {a:11.3f} | {b:16.3f} | {nn:>4}")

    print("\nPar mouvement (embeddings seuls, corpus entier · hors même artiste)")
    for mov, d in sorted(per_mov.items(), key=lambda kv: -mean(kv[1]["emb_x"])):
        extra = ""
        if d["rr_lab"]:
            extra = f"   rerank(sample n={len(d['rr_lab'])}): aveugle {mean(d['rr_blind']):.2f} · avec mouvement {mean(d['rr_lab']):.2f}"
        print(f"  {mov:<20} n={counts[mov]:>3}  emb {mean(d['emb']):.2f} · hors artiste {mean(d['emb_x']):.2f}{extra}")

    result["table"] = [{"method": r[0], "precision": r[1], "precision_cross_artist": r[2], "n": r[3]} for r in rows]
    result["per_movement"] = {m: {k: mean(v) for k, v in d.items() if v} for m, d in per_mov.items()}
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultats enregistrés : {RESULTS_PATH}")


if __name__ == "__main__":
    main()
