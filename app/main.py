from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import RecommendResponse, TasteRequest
from app.recommend import recommend

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="Music Taste Agents", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/", response_class=HTMLResponse)
def index() -> Response:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "provider": settings.llm_provider,
        "model": settings.resolved_model,
        "has_api_key": settings.has_valid_api_key,
    }


@app.post("/api/recommend", response_model=RecommendResponse)
async def api_recommend(body: TasteRequest) -> RecommendResponse:
    if not settings.has_valid_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "GEMINI_API_KEY missing. Get a free key at https://aistudio.google.com/apikey "
                "and paste it into .env"
            ),
        )
    try:
        return await recommend(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
