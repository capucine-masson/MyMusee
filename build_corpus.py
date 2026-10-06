"""Construit le corpus : récupère des peintures du domaine public puis les embarque avec Embed v4.

Sources
  * Art Institute of Chicago (api.artic.edu) : is_public_domain = true, type « Painting »,
    mouvement = style_titles (champ de l'API).
  * Wikidata + Wikimedia Commons : pour les mouvements absents d'AIC une fois filtré sur le domaine public
    (romantisme, expressionnisme, cubisme, art nouveau). Artiste mort avant 1955 ET licence Commons vérifiée.

Le script est IDEMPOTENT et REPRENABLE :
  * les métadonnées sont « upsertées » sans écraser les embeddings existants ;
  * seules les œuvres sans embedding (ou avec un autre modèle) sont ré-embarquées, lot par lot,
    avec sauvegarde après chaque lot : un Ctrl-C ou un quota 429 ne fait rien perdre.

Usage
  python build_corpus.py                 # tout (métadonnées + embeddings)
  python build_corpus.py --scale 0.2     # mini corpus de test (~50 œuvres)
  python build_corpus.py --skip-embed    # métadonnées seulement
  python build_corpus.py --skip-fetch    # embarque seulement ce qui manque
"""
import argparse
import re
import sys
import time
from collections import defaultdict
from urllib.parse import quote, unquote, urlparse

import httpx

import cohere_svc
import config
import db
import imaging
from i18n import AppError

AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# mouvement -> nombre d'œuvres visé
AIC_TARGETS = {
    "Impressionism": 30,
    "Post-Impressionism": 25,
    "Realism": 25,
    "Baroque": 20,
    "Neoclassicism": 11,
    "Renaissance": 25,
    "Mannerism": 8,
}
WIKIDATA_TARGETS = {  # mouvement -> (QID Wikidata, nombre visé)
    "Romanticism": ("Q37068", 30),
    "Expressionism": ("Q80113", 30),
    "Cubism": ("Q42934", 25),
    "Art Nouveau": ("Q34636", 15),
}
MAX_PER_ARTIST = 4


def log(msg: str) -> None:
    print(msg, flush=True)


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=config.HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": config.USER_AGENT, "AIC-User-Agent": config.USER_AGENT},
    )


def request_with_retry(client: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    """Appel HTTP externe : timeout 15 s, backoff sur 429/5xx."""
    delay = 2.0
    last: Exception | None = None
    for _ in range(5):
        try:
            r = client.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                wait = float(r.headers.get("Retry-After", delay)) if r.headers.get("Retry-After", "").isdigit() else delay
                time.sleep(min(wait, 60))
                delay *= 2
                last = RuntimeError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Échec après plusieurs tentatives : {url} ({last})")


def pick_diverse(items: list[dict], n: int) -> list[dict]:
    """Au plus MAX_PER_ARTIST œuvres par artiste, dans l'ordre reçu."""
    count: dict[str, int] = defaultdict(int)
    out = []
    for it in items:
        key = (it.get("artist") or "?").lower()
        if count[key] >= MAX_PER_ARTIST:
            continue
        count[key] += 1
        out.append(it)
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------- AIC
def fetch_aic(client: httpx.Client, movement: str, n: int) -> list[dict]:
    body = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"is_public_domain": True}},
                    {"term": {"artwork_type_title.keyword": "Painting"}},
                    {"exists": {"field": "image_id"}},
                    {"term": {"style_titles.keyword": movement}},
                ]
            }
        },
        "fields": [
            "id", "title", "artist_title", "date_start", "date_display",
            "medium_display", "image_id", "is_public_domain",
        ],
        "limit": 100,
        "page": 1,
    }
    rows: list[dict] = []
    while len(rows) < n * 6 and body["page"] <= 3:
        r = request_with_retry(client, "POST", AIC_SEARCH, json=body).json()
        for a in r.get("data", []):
            if not a.get("is_public_domain") or not a.get("image_id"):
                continue
            rows.append(
                {
                    "id": f"aic:{a['id']}",
                    "title": (a.get("title") or "Untitled").strip(),
                    "artist": (a.get("artist_title") or "").split("\n")[0].strip() or None,
                    "year": a.get("date_start"),
                    "year_display": a.get("date_display"),
                    "movement": movement,
                    "medium": a.get("medium_display"),
                    "image_url": f"https://www.artic.edu/iiif/2/{a['image_id']}/full/843,/0/default.jpg",
                    "source_url": f"https://www.artic.edu/artworks/{a['id']}",
                    "source": "aic",
                    "license": "Public domain (CC0) — Art Institute of Chicago",
                }
            )
        if body["page"] >= r.get("pagination", {}).get("total_pages", 1):
            break
        body["page"] += 1
        time.sleep(0.3)
    return pick_diverse(rows, n)


# --------------------------------------------------------------- Wikidata
SPARQL = """
SELECT ?w (SAMPLE(?wLabel) AS ?title) (SAMPLE(?creatorLabel) AS ?artist)
       (MIN(?inc) AS ?inception) (SAMPLE(?img) AS ?image) (MAX(?sl) AS ?links)
       (GROUP_CONCAT(DISTINCT ?matLabel; separator=", ") AS ?medium)
WHERE {{
  ?w wdt:P31 wd:Q3305213; wdt:P135 wd:{qid}; wdt:P18 ?img; wdt:P170 ?c; wikibase:sitelinks ?sl.
  ?c wdt:P570 ?death. FILTER(YEAR(?death) <= 1954)
  OPTIONAL {{ ?w wdt:P571 ?inc }}
  OPTIONAL {{ ?w wdt:P186 ?mat. ?mat rdfs:label ?matLabel. FILTER(LANG(?matLabel) = "en") }}
  ?w rdfs:label ?wLabel. FILTER(LANG(?wLabel) = "en")
  ?c rdfs:label ?creatorLabel. FILTER(LANG(?creatorLabel) = "en")
}} GROUP BY ?w ORDER BY DESC(?links) LIMIT {limit}
"""


def commons_licenses(client: httpx.Client, filenames: list[str]) -> dict[str, tuple[bool, str]]:
    """Nom de fichier -> (domaine public ?, libellé de licence), via l'API Commons (extmetadata)."""
    out: dict[str, tuple[bool, str]] = {}
    for i in range(0, len(filenames), 25):
        chunk = filenames[i : i + 25]
        params = {
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "extmetadata",
            "redirects": 1, "titles": "|".join("File:" + f for f in chunk),
        }
        data = request_with_retry(client, "GET", COMMONS_API, params=params).json()
        norm = {}
        for n in data.get("query", {}).get("normalized", []) + data.get("query", {}).get("redirects", []):
            norm[n["from"]] = n["to"]
        by_title = {p["title"]: p for p in data.get("query", {}).get("pages", {}).values()}
        for f in chunk:
            title = "File:" + f
            title = norm.get(norm.get(title, title), norm.get(title, title))
            page = by_title.get(title)
            meta = (page or {}).get("imageinfo", [{}])[0].get("extmetadata", {}) if page else {}
            short = (meta.get("LicenseShortName", {}) or {}).get("value", "")
            copyrighted = (meta.get("Copyrighted", {}) or {}).get("value", "True")
            is_pd = copyrighted == "False" or bool(re.match(r"(?i)^(public domain|pd\b|cc0)", short))
            out[f] = (is_pd and bool(short or copyrighted == "False"), short or "Public domain")
        time.sleep(0.3)
    return out


def fetch_wikidata(client: httpx.Client, movement: str, qid: str, n: int) -> list[dict]:
    q = SPARQL.format(qid=qid, limit=max(n * 6, 60))
    r = request_with_retry(
        client, "GET", WIKIDATA_SPARQL, params={"query": q},
        headers={"Accept": "application/sparql-results+json"},
    ).json()
    cands = []
    for b in r["results"]["bindings"]:
        path = urlparse(b["image"]["value"]).path
        filename = unquote(path.split("/Special:FilePath/")[-1])
        if not re.search(r"\.(jpe?g|png|webp)$", filename, re.I):
            continue  # on évite tif/svg/gif, mal gérés en miniature
        inc = b.get("inception", {}).get("value", "")
        year = int(inc[:4]) if re.match(r"^\d{4}", inc) else None
        if year and year > 1954:  # incohérent avec un artiste mort avant 1955 : donnée Wikidata erronée
            year = None
        cands.append(
            {
                "id": "wd:" + b["w"]["value"].rsplit("/", 1)[-1],
                "title": b["title"]["value"].strip(),
                "artist": b["artist"]["value"].strip(),
                "year": year,
                "year_display": str(year) if year else None,
                "movement": movement,
                "medium": b.get("medium", {}).get("value") or None,
                "filename": filename,
                "source": "wikidata",
            }
        )
    cands = pick_diverse(cands, n * 2)
    lic = commons_licenses(client, [c["filename"] for c in cands])
    out = []
    for c in cands:
        fn = c.pop("filename")
        is_pd, label = lic.get(fn, (False, ""))
        if not is_pd:
            continue
        c["image_url"] = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(fn)}?width=800"
        c["source_url"] = "https://commons.wikimedia.org/wiki/File:" + quote(fn.replace(" ", "_"))
        c["license"] = f"{label} — Wikimedia Commons"
        out.append(c)
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ fetch
def fetch_all(scale: float, only: set[str] | None) -> None:
    db.init_db()
    seen: set[tuple[str, str]] = set()
    total_new = 0
    with http_client() as client, db.connect() as conn:
        plan = [("aic", m, n, None) for m, n in AIC_TARGETS.items()] + [
            ("wikidata", m, n, qid) for m, (qid, n) in WIKIDATA_TARGETS.items()
        ]
        for src, movement, n, qid in plan:
            if only and movement.lower() not in only:
                continue
            n = max(2, round(n * scale))
            try:
                items = (
                    fetch_aic(client, movement, n)
                    if src == "aic"
                    else fetch_wikidata(client, movement, qid, n)
                )
            except Exception as e:  # API du corpus indisponible : on continue avec le reste
                log(f"  ! {movement:<20} source « {src} » indisponible ({e}). Ignoré pour l'instant.")
                continue
            kept = 0
            for a in items:
                key = (a["title"].lower(), (a["artist"] or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                db.upsert_artwork(conn, a)
                kept += 1
            total_new += kept
            log(f"  ✓ {movement:<20} {kept:>3} œuvres  ({src})")
    log(f"Métadonnées : {total_new} œuvres enregistrées / mises à jour.")


# ------------------------------------------------------------------ embed
def download_embedding_image(client: httpx.Client, a: dict) -> str | None:
    url = a["image_url"]
    url = url.replace("/full/843,/", f"/full/{config.EMBED_IMAGE_WIDTH},/")
    url = url.replace("width=800", f"width={config.EMBED_IMAGE_WIDTH}")
    try:
        r = request_with_retry(client, "GET", url)
        if not r.content:  # défaut permanent de la source (image vide) : on écarte l'œuvre du corpus
            with db.connect() as conn:
                conn.execute("DELETE FROM artworks WHERE id = ?", (a["id"],))
            log(f"  - « {a['title']} » écartée : la source renvoie une image vide")
            return None
        return imaging.bytes_to_embedding_data_url(r.content)
    except Exception as e:
        log(f"  ! image indisponible pour « {a['title']} » ({e}) — sera retentée au prochain lancement")
        return None


def embed_missing(limit: int | None) -> None:
    todo = db.artworks_to_embed(config.MODEL_EMBED)
    if limit:
        todo = todo[:limit]
    if not todo:
        log("Embeddings : rien à faire, tout est déjà vectorisé.")
        return
    log(f"Embeddings : {len(todo)} œuvres à vectoriser avec {config.MODEL_EMBED}.")
    done = 0
    with http_client() as client:
        for i in range(0, len(todo), cohere_svc.EMBED_BATCH):
            batch = todo[i : i + cohere_svc.EMBED_BATCH]
            urls, kept = [], []
            for a in batch:
                u = download_embedding_image(client, a)
                if u:
                    urls.append(u)
                    kept.append(a)
                time.sleep(0.2)
            if not kept:
                continue
            try:
                vecs, meta = cohere_svc.embed_images(urls, "fr", patient=True)
            except AppError as e:
                log(f"\nArrêt : {e.message}\nRelancez la commande : le travail déjà fait est conservé.")
                sys.exit(1)
            with db.connect() as conn:
                for a, v in zip(kept, vecs):
                    db.save_embedding(conn, a["id"], v, config.MODEL_EMBED)
            done += len(kept)
            log(f"  {done}/{len(todo)}  (lot de {len(kept)} en {meta['ms']} ms)")
    log(f"Embeddings terminés : {done} nouvelles œuvres.")


def summary() -> None:
    s = db.corpus_stats()
    log("\nCorpus actuel : %d œuvres, %d vectorisées" % (s["total"], s["embedded"]))
    for m, n in s["movements"].items():
        log(f"  {m:<22}{n:>4}")
    if len(s["movements"]) < 8:
        log("  ⚠ moins de 8 mouvements : vérifiez les sources indisponibles ci-dessus.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=float, default=1.0, help="multiplicateur des effectifs (0.2 = test rapide)")
    ap.add_argument("--movements", nargs="*", help="limiter à certains mouvements (ex. Impressionism Cubism)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-embed", action="store_true")
    ap.add_argument("--limit-embed", type=int, help="n'embarquer que N œuvres (test de quota)")
    args = ap.parse_args()

    db.init_db()
    if not args.skip_fetch:
        log("Récupération des métadonnées…")
        fetch_all(args.scale, {m.lower() for m in args.movements} if args.movements else None)
    if not args.skip_embed:
        embed_missing(args.limit_embed)
    summary()


if __name__ == "__main__":
    main()
