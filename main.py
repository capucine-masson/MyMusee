"""Musée IA : « Dis-moi ce que tu vois dans ce tableau ». Lancement : python main.py"""
import logging
import re
import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import cohere_svc
import config
import db
import imaging
import search
from i18n import AppError, norm_lang, t

log = logging.getLogger("musee")
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Musée IA", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "static")), name="static")

CSP = (
    "default-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ----------------------------------------------------------------- erreurs
def error_response(key: str, message: str, status: int, detail: str | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": key, "message": message, "detail": detail}}, status_code=status
    )


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return error_response(exc.key, exc.message, exc.status)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("Erreur non gérée sur %s", request.url.path)  # trace côté serveur uniquement
    return error_response("internal", t(request.headers.get("x-lang"), "internal"), 500)


# ------------------------------------------------------------------- pages
@app.get("/")
def index(request: Request):
    prefs = db.get_preferences()
    boot = {
        "prefs": prefs,
        "history": db.list_history(10),
        "status": status_payload(),
        "models": models_payload(),
    }
    return templates.TemplateResponse(request, "index.html", {"boot": boot, "page": "index"})


@app.get("/salle")
def salle(request: Request):
    boot = {"prefs": db.get_preferences(), "models": models_payload()}
    return templates.TemplateResponse(request, "salle.html", {"boot": boot, "page": "salle"})


# --------------------------------------------------------------------- API
def models_payload() -> dict:
    return {
        "vision": config.MODEL_VISION,
        "chat": config.MODEL_CHAT,
        "embed": config.MODEL_EMBED,
        "rerank": config.MODEL_RERANK,
    }


def status_payload() -> dict:
    stats = db.corpus_stats()
    return {
        "has_key": bool(config.COHERE_API_KEY),
        "corpus_total": stats["total"],
        "corpus_embedded": stats["embedded"],
        "movements": len(stats["movements"]),
    }


@app.get("/api/status")
def api_status():
    return {**status_payload(), "models": models_payload()}


@app.get("/api/ping")
def api_ping(request: Request):
    """Prouve que la clé Cohere fonctionne (un appel minimal)."""
    return cohere_svc.ping(norm_lang(request.headers.get("x-lang")))


class SettingsIn(BaseModel):
    lang: str | None = None
    level: str | None = None


@app.get("/api/settings")
def api_get_settings():
    return db.get_preferences()


@app.put("/api/settings")
def api_put_settings(body: SettingsIn):
    if body.lang is not None:
        if body.lang not in config.LANGS:
            raise AppError("bad_request", 422, None)
        db.set_setting("lang", body.lang)
    if body.level is not None:
        if body.level not in config.LEVELS:
            raise AppError("bad_request", 422, None)
        db.set_setting("level", body.level)
    return db.get_preferences()


@app.get("/api/history")
def api_history():
    return db.list_history(10)


@app.get("/api/history/{history_id}")
def api_history_item(history_id: int, request: Request):
    item = db.get_history(history_id)
    if not item:
        raise AppError("not_found", 404, request.headers.get("x-lang"))
    return item


@app.delete("/api/history")
def api_history_clear():
    db.clear_history()
    return {"ok": True}


ART_ID_RE = re.compile(r"^(aic|wd):[A-Za-z0-9-]{1,40}$")


@app.get("/art/{artwork_id}")
def art_image(artwork_id: str):
    """Proxy d'images du corpus : l'URL source vient de la base (jamais du client → pas de SSRF).

    Nécessaire car AIC exige un en-tête AIC-User-Agent qu'un <img> ne peut pas envoyer, et pour garder
    une CSP stricte (img-src 'self'). Les images du domaine public sont mises en cache sur disque.
    """
    if not ART_ID_RE.match(artwork_id):
        return Response(status_code=404)
    cache = config.ART_CACHE_DIR / (artwork_id.replace(":", "_") + ".img")
    headers = {"Cache-Control": "public, max-age=86400"}
    if cache.exists():
        return Response(cache.read_bytes(), media_type="image/jpeg", headers=headers)

    source = db.get_artwork_source_image(artwork_id)
    if not source:
        return Response(status_code=404)
    try:
        with httpx.Client(
            timeout=config.HTTP_TIMEOUT, follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT, "AIC-User-Agent": config.USER_AGENT},
        ) as client:
            r = client.get(source)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) > config.MAX_ART_BYTES:
            return Response(status_code=502)
    except httpx.HTTPError:
        return Response(status_code=502)
    config.ART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(r.content)
    return Response(r.content, media_type=ctype.split(";")[0], headers=headers)


@app.get("/api/corpus")
def api_corpus():
    return {"stats": db.corpus_stats(), **search.pca_2d()}


def read_upload(image: UploadFile, lang: str):
    raw = image.file.read(config.MAX_UPLOAD_BYTES + 1)  # lecture bornée : jamais plus de 5 Mo + 1 octet
    return imaging.validate_upload(raw, image.content_type, lang)


def check_level(level: str) -> str:
    return level if level in config.LEVELS else config.DEFAULT_LEVEL


@app.post("/api/analyze")
def api_analyze(
    image: UploadFile = File(...),
    lang: str = Form("fr"),
    level: str = Form("enthusiast"),
):
    """Étape 1 : Command A Vision → analyse structurée. L'image reste en mémoire."""
    lang, level = norm_lang(lang), check_level(level)
    img = read_upload(image, lang)
    analysis, meta = cohere_svc.analyze_image(imaging.for_vision(img), level, lang)

    if not analysis["is_painting"]:
        return error_response(
            "not_painting", t(lang, "not_painting"), 422, analysis["not_painting_reason"] or None
        )

    summary = analysis["movement"] or "?"
    if analysis["artist_guess"]:
        summary += f" · {analysis['artist_guess']}"
    result = {"analysis": analysis, "timings": [meta], "neighbors": [], "before": [], "grounding": None}
    history_id = db.add_history(lang, level, summary[:200], result)
    return {"history_id": history_id, "lang": lang, "level": level, **result}


def neighbor_payload(a: dict, cosine: float, rank_before: int, rerank_score: float | None = None) -> dict:
    return {
        "id": a["id"],
        "title": a["title"],
        "artist": a["artist"],
        "year": a["year_display"],
        "movement": a["movement"],
        "medium": a["medium"],
        "image_url": db.art_url(a["id"]),
        "source_url": a["source_url"],
        "license": a["license"],
        "cosine": round(cosine, 4),
        "rank_before": rank_before,
        "rerank_score": None if rerank_score is None else round(rerank_score, 4),
    }


@app.post("/api/similar")
def api_similar(
    image: UploadFile = File(...),
    history_id: int = Form(...),
    lang: str = Form("fr"),
):
    """Étape 2 : embedding de l'image → top 20 cosinus → rerank → top 5 → explication groundée."""
    lang = norm_lang(lang)
    item = db.get_history(history_id)
    if not item:
        raise AppError("not_found", 404, lang)
    analysis, level = item["result"]["analysis"], check_level(item["level"])
    timings = [item["result"]["timings"][0]]

    if not search.load_index()[0]:
        raise AppError("corpus_empty", 503, lang)

    img = read_upload(image, lang)
    vecs, meta = cohere_svc.embed_images([imaging.for_embedding(img)], lang)
    timings.append(meta)

    t0 = time.perf_counter()
    candidates = search.top_k(vecs[0], config.CANDIDATES_K)
    timings.append(
        {"step": "search", "model": f"numpy cosine · {len(search.load_index()[0])} œuvres",
         "ms": round((time.perf_counter() - t0) * 1000, 1)}
    )
    if not candidates:
        raise AppError("no_similar", 404, lang)

    metas = [c[0] for c in candidates]
    cosines = [c[1] for c in candidates]
    before = [neighbor_payload(metas[i], cosines[i], i + 1) for i in range(min(config.FINAL_K, len(metas)))]

    errors: dict[str, str] = {}
    try:
        ranked, meta = cohere_svc.rerank(
            analysis["search_description_en"], metas, config.FINAL_K, lang
        )
        timings.append(meta)
        final = [neighbor_payload(metas[i], cosines[i], i + 1, score) for i, score in ranked]
    except AppError as e:  # dégradation douce : on garde l'ordre des embeddings
        errors["rerank"] = e.message
        final = before

    grounding = None
    try:
        grounding, meta = cohere_svc.ground_explanation(
            analysis, [{**f, "year_display": f["year"]} for f in final], level, lang
        )
        timings.append(meta)
    except AppError as e:
        errors["grounding"] = e.message

    result = {
        "analysis": analysis,
        "neighbors": final,
        "before": before,
        "grounding": grounding,
        "timings": timings,
        "errors": errors,
    }
    db.update_history(history_id, result)
    return {"history_id": history_id, **result}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
