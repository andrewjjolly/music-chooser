from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, load_settings
from .db import initialize
from .dates import buckets_for, local_today, week_key
from .metacritic import MetacriticClient
from .recommendations import RecommendationService
from .repositories import CatalogRepository
from .services import SyncService


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    initialize(settings.db_path)
    repository = CatalogRepository(settings.db_path)
    sync_service = SyncService(settings, repository)
    recommendation_service = RecommendationService(repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_sync:
            await asyncio.to_thread(sync_service.sync_recent_if_stale)
        yield

    app = FastAPI(title="Music Chooser", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.state.settings = settings
    app.state.repository = repository
    app.state.sync_service = sync_service
    app.state.recommendation_service = recommendation_service

    def context(request: Request, **extra):
        return {"request": request, "settings": settings, "today": local_today(settings.timezone), **extra}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        current = repository.latest_sync()
        albums = repository.list_albums(sort="release_date", descending=True)[:10]
        week = repository.weekly_set(week_key(local_today(settings.timezone)))
        return templates.TemplateResponse(request, "dashboard.html", context(request, latest_sync=current, albums=albums, week=week))

    @app.get("/albums", response_class=HTMLResponse)
    def albums(request: Request, q: str = "", sort: str = "release_date", direction: str = "desc"):
        return templates.TemplateResponse(request, "albums.html", context(request, albums=repository.list_albums(q, sort, direction != "asc"), q=q, sort=sort, direction=direction))

    @app.post("/albums/{album_id}/listening")
    async def update_listening(request: Request, album_id: int):
        data = parse_qs((await request.body()).decode())
        state = data.get("state", ["unheard"])[0]
        sentiment = data.get("sentiment", [None])[0] or None
        rating_raw = data.get("rating", [""])[0]
        rating = int(rating_raw) if rating_raw.isdigit() else None
        note = data.get("note", [""])[0].strip() or None
        repository.update_listening(album_id, state, sentiment, rating, note)
        return RedirectResponse(request.headers.get("referer", "/albums"), status_code=303)

    @app.post("/sync")
    def sync():
        sync_service.sync_recent_if_stale(force=True)
        return RedirectResponse("/", status_code=303)

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request):
        return templates.TemplateResponse(request, "import.html", context(request, result=None))

    @app.post("/import")
    async def import_urls(request: Request):
        data = parse_qs((await request.body()).decode())
        raw = data.get("urls", [""])[0]
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        try:
            result = sync_service.import_urls(urls)
        except Exception as exc:
            result = {"status": "failed", "errors": [str(exc)], "albums": 0, "request_count": 0}
        return templates.TemplateResponse(request, "import.html", context(request, result=result))

    @app.get("/chooser", response_class=HTMLResponse)
    def chooser(request: Request):
        today = local_today(settings.timezone)
        current_week_key = week_key(today)
        weekly_id = repository.create_or_get_week(current_week_key)
        week = repository.weekly_set(current_week_key)
        buckets = buckets_for(today)
        position = len(week["albums"]) + 1 if week else 1
        bucket = buckets[position - 1] if position <= 5 else buckets[-1]
        candidates = recommendation_service.recommend(bucket, weekly_id)
        return templates.TemplateResponse(request, "chooser.html", context(request, week=week, bucket=bucket, candidates=candidates, position=position, complete=bool(week and week["status"] == "complete")))

    @app.post("/chooser/accept")
    async def accept(request: Request):
        data = parse_qs((await request.body()).decode())
        album_id = int(data["album_id"][0])
        bucket_key = data["bucket_key"][0]
        current_week_key = week_key(local_today(settings.timezone))
        weekly_id = repository.create_or_get_week(current_week_key)
        position = len(repository.weekly_set(current_week_key)["albums"]) + 1
        repository.accept_album(weekly_id, album_id, bucket_key, position)
        return RedirectResponse("/chooser", status_code=303)

    @app.post("/chooser/reject")
    async def reject(request: Request):
        data = parse_qs((await request.body()).decode())
        current_week_key = week_key(local_today(settings.timezone))
        weekly_id = repository.create_or_get_week(current_week_key)
        repository.reject_album(weekly_id, int(data["album_id"][0]), data["bucket_key"][0])
        return RedirectResponse("/chooser", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return templates.TemplateResponse(request, "settings.html", context(request, latest_sync=repository.latest_sync()))

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("music_chooser.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=False)


if __name__ == "__main__":
    run()
