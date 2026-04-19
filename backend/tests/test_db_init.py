"""Tests for the DB lazy-init path and schema."""

from __future__ import annotations

import sqlite3

import pytest

from db import DB_PATH, get_conn, init_db
from db.seed import DEFAULT_TICKERS


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    # The module-level DB_PATH is resolved at import time; override for tests.
    import db as db_pkg
    monkeypatch.setattr(db_pkg, "DB_PATH", path)
    yield path


def test_init_creates_tables_and_seeds(tmp_db):
    init_db(tmp_db)

    with get_conn(tmp_db) as conn:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"users_profile", "watchlist", "positions", "trades",
                "portfolio_snapshots", "chat_messages"}.issubset(tables)

        cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id='default'"
        ).fetchone()[0]
        assert cash == 10000.0

        tickers = {
            r[0] for r in conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id='default'"
            )
        }
        assert tickers == set(DEFAULT_TICKERS)


def test_init_is_idempotent(tmp_db):
    init_db(tmp_db)
    init_db(tmp_db)  # second call must not double-seed

    with get_conn(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        assert count == len(DEFAULT_TICKERS)
        profiles = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
        assert profiles == 1


def test_unique_user_ticker_watchlist(tmp_db):
    init_db(tmp_db)
    with get_conn(tmp_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) "
                "VALUES ('x', 'default', 'AAPL', '2026-01-01T00:00:00Z')"
            )


def test_unique_user_ticker_positions(tmp_db):
    init_db(tmp_db)
    with get_conn(tmp_db) as conn:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES ('p1', 'default', 'AAPL', 1.0, 100.0, '2026-01-01T00:00:00Z')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                "VALUES ('p2', 'default', 'AAPL', 2.0, 110.0, '2026-01-01T00:00:00Z')"
            )


def test_foreign_keys_and_wal_enabled(tmp_db):
    init_db(tmp_db)
    with get_conn(tmp_db) as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert fk == 1
        assert journal.lower() == "wal"
