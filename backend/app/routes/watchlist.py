"""Watchlist CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from db import get_conn, iso_now
from ..schemas import WatchlistAddRequest, WatchlistEntryOut, WatchlistOut

router = APIRouter(prefix="/api/watchlist")

USER = "default"


def _current(conn) -> WatchlistOut:
    rows = conn.execute(
        "SELECT ticker, added_at FROM watchlist WHERE user_id=? ORDER BY added_at",
        (USER,),
    ).fetchall()
    return WatchlistOut(watchlist=[
        WatchlistEntryOut(
            ticker=r[0],
            price=None,
            previous_price=None,
            added_at=r[1],
        )
        for r in rows
    ])


def _with_prices(wl: WatchlistOut, provider) -> WatchlistOut:
    out: list[WatchlistEntryOut] = []
    for e in wl.watchlist:
        p = provider.get_price(e.ticker) if provider else None
        out.append(WatchlistEntryOut(
            ticker=e.ticker,
            price=p.price if p else None,
            previous_price=p.previous_price if p else None,
            added_at=e.added_at,
        ))
    return WatchlistOut(watchlist=out)


@router.get("")
@router.get("/")
def list_watchlist(request: Request) -> WatchlistOut:
    with get_conn() as conn:
        wl = _current(conn)
    return _with_prices(wl, getattr(request.app.state, "market", None))


@router.post("")
@router.post("/")
def add(body: WatchlistAddRequest, request: Request) -> WatchlistOut:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM watchlist WHERE user_id=? AND ticker=?",
            (USER, body.ticker),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), USER, body.ticker, iso_now()),
            )
        wl = _current(conn)

    provider = getattr(request.app.state, "market", None)
    if provider is not None:
        provider.add_ticker(body.ticker)
    return _with_prices(wl, provider)


@router.delete("/{ticker}")
def remove(ticker: str, request: Request) -> WatchlistOut:
    ticker = ticker.strip().upper()
    with get_conn() as conn:
        res = conn.execute(
            "DELETE FROM watchlist WHERE user_id=? AND ticker=?", (USER, ticker)
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")
        wl = _current(conn)

    provider = getattr(request.app.state, "market", None)
    if provider is not None:
        # Only stop tracking if no other watchlist keeps it; single-user so yes.
        provider.remove_ticker(ticker)
    return _with_prices(wl, provider)
