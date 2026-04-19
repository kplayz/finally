"""Database package for FinAlly.

SQLite single-writer: all writes go through a single connection at a time.
Readers can be concurrent (WAL mode), writers serialize. Keep DB operations
short; do not hold a write transaction across an ``await``.

Public API:
    DB_PATH       -- resolved Path to the sqlite file
    get_conn()    -- context manager yielding a configured sqlite3.Connection
    init_db()     -- idempotent: create schema + seed defaults if missing
    iso_now()     -- ISO-8601 UTC timestamp string
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "finally.db"
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


def _resolve_db_path() -> Path:
    override = os.environ.get("FINALLY_DB_PATH")
    return Path(override) if override else _DEFAULT_DB_PATH


# Exposed as a module attribute for convenience; tests reach into this.
DB_PATH: Path = _resolve_db_path()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 Connection with FK + WAL enabled. Commits on clean exit."""
    path = Path(db_path) if db_path else _resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        yield conn
    finally:
        conn.close()


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def init_db(db_path: Path | None = None) -> None:
    """Create schema and seed defaults if any expected table is missing.

    Safe to call repeatedly — no-op when already initialized.
    """
    from .seed import seed_defaults

    with get_conn(db_path) as conn:
        if _EXPECTED_TABLES.issubset(_existing_tables(conn)):
            return
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        seed_defaults(conn)
