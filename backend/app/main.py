"""FastAPI application for FinAlly.

Wires: DB lazy-init, market data provider, SSE stream, REST routes,
static frontend, and the portfolio snapshot background task.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from db import get_conn, init_db
from market import create_provider

from .config import load_settings
from .logging import setup_logging
from .routes import chat, portfolio, stream, system, watchlist
from .tasks import snapshot_loop

log = logging.getLogger(__name__)


def _initial_tickers() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id='default'"
        ).fetchall()
    return [r[0] for r in rows]


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = load_settings()
    app.state.settings = settings
    app.state.sse_cadence_s = settings.sse_cadence_ms / 1000.0

    init_db(settings.db_path)

    tickers = _initial_tickers()
    provider = create_provider(tickers)
    await provider.start()
    app.state.market = provider

    snapshot_task = asyncio.create_task(
        snapshot_loop(
            get_provider=lambda: app.state.market,
            interval_s=settings.snapshot_interval_s,
            retention_hours=settings.snapshot_retention_hours,
        ),
        name="portfolio-snapshot-loop",
    )
    log.info("finally started", extra={"extra_fields": {"db": str(settings.db_path)}})

    try:
        yield
    finally:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except (asyncio.CancelledError, Exception):
            pass
        await provider.stop()
        log.info("finally stopped")


app = FastAPI(title="FinAlly", lifespan=lifespan)

# Mount API routers first so /api/* always wins over static.
app.include_router(system.router)
app.include_router(watchlist.router)
app.include_router(portfolio.router)
app.include_router(chat.router)
app.include_router(stream.router)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/stream/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


app.add_middleware(CacheControlMiddleware)


def _mount_static() -> None:
    settings = load_settings()
    static_dir = settings.static_dir
    if static_dir is None or not static_dir.is_dir():
        return

    index = static_dir / "index.html"

    app.mount("/_next", StaticFiles(directory=str(static_dir / "_next"), check_dir=False), name="next")
    app.mount(
        "/static", StaticFiles(directory=str(static_dir), check_dir=False), name="static"
    )

    @app.get("/")
    async def root_index():
        if index.is_file():
            return FileResponse(index)
        return {"message": "frontend not built"}

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # API routes are registered above; anything else falls back to
        # serving a file if it exists, else index.html (SPA shell).
        if full_path.startswith("api/") or full_path.startswith("_next/"):
            # These are handled above; let FastAPI's 404 surface if we reach here.
            return {"detail": "Not Found"}, 404
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        return {"detail": "Not Found"}, 404


_mount_static()
