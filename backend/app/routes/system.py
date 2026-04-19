"""Health, readiness, and account reset."""

from __future__ import annotations

from fastapi import APIRouter, Request

from db import get_conn
from db.reset import reset_account

router = APIRouter()


@router.get("/api/health")
@router.get("/healthz")
def health():
    return {"status": "ok"}


@router.get("/readyz")
def ready(request: Request):
    # Ready = DB reachable + market provider started.
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:  # pragma: no cover
        return {"status": "not_ready", "reason": f"db: {exc}"}
    provider = getattr(request.app.state, "market", None)
    if provider is None:
        return {"status": "not_ready", "reason": "market provider not started"}
    return {"status": "ready"}


@router.post("/api/reset")
def reset(request: Request):
    with get_conn() as conn:
        reset_account(conn)
    # Re-sync the market provider's ticker set with the (restored) watchlist.
    provider = getattr(request.app.state, "market", None)
    if provider is not None:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id='default'"
            ).fetchall()
        tracked = set(provider.get_all_prices().keys())
        desired = {r[0] for r in rows}
        for t in desired - tracked:
            provider.add_ticker(t)
        for t in tracked - desired:
            provider.remove_ticker(t)
    return {"ok": True}
