"""Portfolio REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from db import get_conn
from ..portfolio import TradeError, compute_total_value, execute_trade
from ..schemas import (
    PortfolioHistoryOut,
    PortfolioOut,
    PositionOut,
    Snapshot,
    TradeRequest,
    TradeResponse,
)
from ..tasks import record_snapshot

router = APIRouter(prefix="/api/portfolio")
USER = "default"


def _price_lookup(provider):
    def lookup(ticker: str) -> float | None:
        if provider is None:
            return None
        p = provider.get_price(ticker)
        return p.price if p else None
    return lookup


@router.get("")
@router.get("/")
def get_portfolio(request: Request) -> PortfolioOut:
    provider = getattr(request.app.state, "market", None)
    lookup = _price_lookup(provider)
    with get_conn() as conn:
        cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id=?", (USER,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id=?", (USER,)
        ).fetchall()

    positions: list[PositionOut] = []
    total_positions_value = 0.0
    for t, qty, avg in rows:
        current = lookup(t) if lookup else None
        if current is None:
            current = float(avg)
        qty = float(qty)
        avg = float(avg)
        unrealized = (current - avg) * qty
        pct = ((current - avg) / avg * 100.0) if avg != 0 else 0.0
        positions.append(PositionOut(
            ticker=t,
            quantity=qty,
            avg_cost=avg,
            current_price=current,
            unrealized_pnl=unrealized,
            pnl_percent=pct,
        ))
        total_positions_value += qty * current

    return PortfolioOut(
        cash_balance=float(cash),
        total_value=float(cash) + total_positions_value,
        positions=positions,
    )


@router.post("/trade")
def trade(body: TradeRequest, request: Request) -> TradeResponse:
    provider = getattr(request.app.state, "market", None)
    price_pt = provider.get_price(body.ticker) if provider else None
    if price_pt is None:
        raise HTTPException(
            status_code=400,
            detail=f"no live price for {body.ticker}; add it to the watchlist first",
        )

    with get_conn() as conn:
        try:
            res = execute_trade(
                conn,
                user_id=USER,
                ticker=body.ticker,
                side=body.side,
                quantity=body.quantity,
                price=price_pt.price,
            )
        except TradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # Immediate snapshot after each trade (plus the periodic 30s one).
    with get_conn() as conn:
        total = compute_total_value(conn, USER, _price_lookup(provider))
        record_snapshot(conn, USER, total)

    return TradeResponse(**res.__dict__)


@router.get("/history")
def history() -> PortfolioHistoryOut:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT total_value, recorded_at FROM portfolio_snapshots"
            " WHERE user_id=? ORDER BY recorded_at",
            (USER,),
        ).fetchall()
    return PortfolioHistoryOut(
        snapshots=[Snapshot(total_value=float(r[0]), recorded_at=r[1]) for r in rows]
    )
