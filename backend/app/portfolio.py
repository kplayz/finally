"""Portfolio math and trade execution. Pure DB operations; no HTTP concerns.

All writes happen through this module so we can test them without spinning
up the full FastAPI app and so the LLM engineer can auto-execute trades
via the same code path as manual trades.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from db import iso_now

QTY_TOL = 1e-9  # below this, treat as zero


class TradeError(Exception):
    """Raised when a trade fails validation."""


@dataclass
class TradeResult:
    ticker: str
    side: str
    quantity: float
    price: float
    total_cost: float
    cash_remaining: float


def get_cash(conn: sqlite3.Connection, user_id: str = "default") -> float:
    row = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise TradeError("user profile not found")
    return float(row[0])


def get_position(conn: sqlite3.Connection, user_id: str, ticker: str) -> tuple[float, float] | None:
    """Return (quantity, avg_cost) or None if the position does not exist."""
    row = conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id=? AND ticker=?",
        (user_id, ticker),
    ).fetchone()
    return (float(row[0]), float(row[1])) if row else None


def execute_trade(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
) -> TradeResult:
    """Execute a market order atomically. Raises TradeError on validation failure.

    Caller is responsible for resolving *price* from the live price cache.
    """
    if side not in ("buy", "sell"):
        raise TradeError(f"invalid side: {side}")
    if quantity <= 0:
        raise TradeError("quantity must be positive")
    if price <= 0:
        raise TradeError("price must be positive")

    ticker = ticker.upper()
    total_cost = quantity * price
    now = iso_now()

    conn.execute("BEGIN IMMEDIATE")
    try:
        cash = get_cash(conn, user_id)
        existing = get_position(conn, user_id, ticker)

        if side == "buy":
            if total_cost > cash + 1e-9:
                raise TradeError(
                    f"insufficient cash: need ${total_cost:.2f}, have ${cash:.2f}"
                )
            new_cash = cash - total_cost
            if existing is None:
                conn.execute(
                    "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), user_id, ticker, quantity, price, now),
                )
            else:
                cur_qty, cur_avg = existing
                new_qty = cur_qty + quantity
                new_avg = ((cur_qty * cur_avg) + (quantity * price)) / new_qty
                conn.execute(
                    "UPDATE positions SET quantity=?, avg_cost=?, updated_at=?"
                    " WHERE user_id=? AND ticker=?",
                    (new_qty, new_avg, now, user_id, ticker),
                )
        else:  # sell
            if existing is None:
                raise TradeError(f"no position in {ticker} to sell")
            cur_qty, cur_avg = existing
            if quantity > cur_qty + 1e-9:
                raise TradeError(
                    f"cannot sell {quantity} {ticker}: only {cur_qty} held"
                )
            new_cash = cash + total_cost
            new_qty = cur_qty - quantity
            if new_qty <= QTY_TOL:
                conn.execute(
                    "DELETE FROM positions WHERE user_id=? AND ticker=?",
                    (user_id, ticker),
                )
            else:
                conn.execute(
                    "UPDATE positions SET quantity=?, updated_at=? WHERE user_id=? AND ticker=?",
                    (new_qty, now, user_id, ticker),
                )

        conn.execute(
            "UPDATE users_profile SET cash_balance=? WHERE id=?",
            (new_cash, user_id),
        )
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, ticker, side, quantity, price, now),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return TradeResult(
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        total_cost=total_cost,
        cash_remaining=new_cash,
    )


def compute_total_value(
    conn: sqlite3.Connection,
    user_id: str,
    price_lookup: "callable[[str], float | None]",
) -> float:
    """Sum cash + (quantity × current price) across positions."""
    cash = get_cash(conn, user_id)
    positions = conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id=?",
        (user_id,),
    ).fetchall()
    total = cash
    for t, qty, avg_cost in positions:
        live = price_lookup(t)
        total += float(qty) * float(live if live is not None else avg_cost)
    return total
