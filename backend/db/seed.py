"""Default seed data for a fresh FinAlly database."""

from __future__ import annotations

import sqlite3
import uuid

from . import iso_now

DEFAULT_USER_ID = "default"
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS: tuple[str, ...] = (
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
)


def seed_defaults(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> None:
    """Seed the default user profile and watchlist. Idempotent per row."""
    now = iso_now()

    conn.execute(
        """INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at)
           VALUES (?, ?, ?)""",
        (user_id, DEFAULT_CASH, now),
    )

    existing = conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    if existing == 0:
        conn.executemany(
            """INSERT INTO watchlist (id, user_id, ticker, added_at)
               VALUES (?, ?, ?, ?)""",
            [(str(uuid.uuid4()), user_id, t, now) for t in DEFAULT_TICKERS],
        )
