"""Top-level /api/chat handler: build context → call LLM → auto-execute actions."""

from __future__ import annotations

import json
import logging
import uuid

from db import get_conn, iso_now
from ..config import load_settings
from ..portfolio import TradeError, compute_total_value, execute_trade
from ..schemas import ChatResponse, ChatTrade, WatchlistChange
from .mock import mock_respond
from .prompts import SYSTEM_PROMPT, build_context_message, load_recent_history
from .schema import LLMOutput

log = logging.getLogger(__name__)
USER = "default"


def _gather_context(conn, provider) -> tuple[float, float, list[dict], list[dict]]:
    cash = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id=?", (USER,)
    ).fetchone()[0]
    pos_rows = conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id=?",
        (USER,),
    ).fetchall()
    positions: list[dict] = []
    for t, qty, avg in pos_rows:
        price_pt = provider.get_price(t) if provider else None
        current = price_pt.price if price_pt else float(avg)
        positions.append({
            "ticker": t,
            "quantity": float(qty),
            "avg_cost": float(avg),
            "current_price": current,
            "unrealized_pnl": (current - float(avg)) * float(qty),
            "pnl_percent": ((current - float(avg)) / float(avg) * 100.0) if float(avg) else 0.0,
        })
    wl_rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id=?", (USER,)
    ).fetchall()
    watchlist: list[dict] = []
    for (t,) in wl_rows:
        price_pt = provider.get_price(t) if provider else None
        watchlist.append({"ticker": t, "price": price_pt.price if price_pt else None})

    def lookup(ticker: str):
        p = provider.get_price(ticker) if provider else None
        return p.price if p else None

    total = compute_total_value(conn, USER, lookup)
    return float(cash), total, positions, watchlist


def _apply_actions(
    conn,
    provider,
    output: LLMOutput,
) -> tuple[list[ChatTrade], list[WatchlistChange], list[str]]:
    applied_trades: list[ChatTrade] = []
    applied_watch: list[WatchlistChange] = []
    errors: list[str] = []

    for t in output.trades:
        price_pt = provider.get_price(t.ticker) if provider else None
        if price_pt is None:
            errors.append(f"{t.ticker}: no live price (add it to watchlist first)")
            continue
        try:
            res = execute_trade(
                conn,
                user_id=USER,
                ticker=t.ticker,
                side=t.side,
                quantity=t.quantity,
                price=price_pt.price,
            )
            applied_trades.append(ChatTrade(
                ticker=res.ticker, side=res.side, quantity=res.quantity, price=res.price
            ))
        except TradeError as exc:
            errors.append(f"{t.ticker} {t.side} {t.quantity}: {exc}")

    for wc in output.watchlist_changes:
        ticker = wc.ticker.strip().upper()
        if wc.action == "add":
            existing = conn.execute(
                "SELECT 1 FROM watchlist WHERE user_id=? AND ticker=?",
                (USER, ticker),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?,?,?,?)",
                    (str(uuid.uuid4()), USER, ticker, iso_now()),
                )
                if provider:
                    provider.add_ticker(ticker)
            applied_watch.append(WatchlistChange(ticker=ticker, action="add"))
        else:
            res = conn.execute(
                "DELETE FROM watchlist WHERE user_id=? AND ticker=?", (USER, ticker)
            )
            if res.rowcount:
                if provider:
                    provider.remove_ticker(ticker)
                applied_watch.append(WatchlistChange(ticker=ticker, action="remove"))
            else:
                errors.append(f"{ticker}: not in watchlist")

    return applied_trades, applied_watch, errors


def _persist_messages(conn, user_msg: str, assistant_msg: str, actions: dict) -> None:
    now = iso_now()
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), USER, "user", user_msg, None, now),
    )
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), USER, "assistant", assistant_msg, json.dumps(actions), now),
    )


async def handle_chat(user_message: str, *, provider) -> ChatResponse:
    settings = load_settings()

    with get_conn() as conn:
        cash, total, positions, watchlist = _gather_context(conn, provider)
        history = load_recent_history(conn, USER, limit=20)

    ctx_msg = build_context_message(
        cash=cash, total_value=total, positions=positions, watchlist=watchlist
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": ctx_msg},
        *history,
        {"role": "user", "content": user_message},
    ]

    if settings.llm_mock or not settings.openrouter_api_key:
        output = mock_respond(user_message, watchlist=[w["ticker"] for w in watchlist])
    else:
        from .client import call_llm
        try:
            output = await call_llm(messages, model=settings.llm_model)
        except Exception as exc:
            log.exception("LLM call failed")
            return ChatResponse(
                message=f"(LLM error: {exc})",
                trades=[], watchlist_changes=[], errors=[str(exc)],
            )

    with get_conn() as conn:
        trades, wchanges, errors = _apply_actions(conn, provider, output)
        _persist_messages(
            conn,
            user_msg=user_message,
            assistant_msg=output.message,
            actions={
                "trades": [t.model_dump() for t in trades],
                "watchlist_changes": [w.model_dump() for w in wchanges],
                "errors": errors,
            },
        )

    return ChatResponse(
        message=output.message,
        trades=trades,
        watchlist_changes=wchanges,
        errors=errors,
    )
