"""System prompt + context assembly for the chat LLM."""

from __future__ import annotations

import json
import sqlite3

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant embedded in a simulated trading \
workstation. The user has a portfolio of fake-money positions and a watchlist \
of live-priced tickers. You can:
  - analyze portfolio composition, risk concentration, and realized/unrealized P&L
  - suggest trades with clear reasoning
  - execute trades on the user's behalf (market orders, simulated fills)
  - manage the watchlist (add/remove tickers)

Be concise and data-driven. Prefer short sentences with concrete numbers.
When asked to trade, include the trade in the `trades` array. When adjusting
the watchlist, include entries in `watchlist_changes`. If the user asks a
question without requiring action, leave both arrays empty.

You MUST respond with a JSON object matching the provided schema.
"""


def _fmt_positions(positions: list[dict]) -> str:
    if not positions:
        return "(no open positions)"
    lines = []
    for p in positions:
        lines.append(
            f"  {p['ticker']}: qty={p['quantity']:.4f}, "
            f"avg_cost=${p['avg_cost']:.2f}, "
            f"current=${p['current_price']:.2f}, "
            f"pnl=${p['unrealized_pnl']:.2f} ({p['pnl_percent']:+.2f}%)"
        )
    return "\n".join(lines)


def _fmt_watchlist(wl: list[dict]) -> str:
    if not wl:
        return "(empty)"
    return ", ".join(
        f"{e['ticker']}@${e['price']:.2f}" if e.get("price") is not None else e["ticker"]
        for e in wl
    )


def build_context_message(
    *,
    cash: float,
    total_value: float,
    positions: list[dict],
    watchlist: list[dict],
) -> str:
    return (
        "PORTFOLIO CONTEXT\n"
        f"  cash: ${cash:.2f}\n"
        f"  total_value: ${total_value:.2f}\n"
        "  positions:\n"
        f"{_fmt_positions(positions)}\n"
        f"  watchlist: {_fmt_watchlist(watchlist)}\n"
    )


def load_recent_history(
    conn: sqlite3.Connection, user_id: str, limit: int = 20
) -> list[dict]:
    """Return the last ``limit`` chat messages ordered oldest → newest."""
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE user_id=?"
        " ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    msgs = [{"role": r[0], "content": r[1]} for r in rows]
    msgs.reverse()
    return msgs
