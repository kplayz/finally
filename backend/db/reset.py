"""Account reset — returns the DB to seed state for a user."""

from __future__ import annotations

import sqlite3

from .seed import DEFAULT_CASH, DEFAULT_USER_ID, seed_defaults


def reset_account(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> None:
    """Wipe user-owned rows and re-seed defaults in a single transaction."""
    conn.execute("BEGIN")
    try:
        for table in ("positions", "trades", "portfolio_snapshots",
                      "chat_messages", "watchlist"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))

        # Preserve created_at if the user row already exists; just reset cash.
        result = conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (DEFAULT_CASH, user_id),
        )
        if result.rowcount == 0:
            # Brand-new user — seed_defaults will create the profile row.
            pass

        seed_defaults(conn, user_id=user_id)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
