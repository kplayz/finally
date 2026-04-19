"""Tests for reset_account()."""

from __future__ import annotations

import pytest

from db import get_conn, init_db, iso_now
from db.reset import reset_account
from db.seed import DEFAULT_TICKERS


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    import db as db_pkg
    monkeypatch.setattr(db_pkg, "DB_PATH", path)
    init_db(path)
    return path


def test_reset_restores_seed_state(tmp_db):
    with get_conn(tmp_db) as conn:
        # Dirty the DB.
        conn.execute(
            "UPDATE users_profile SET cash_balance = 1.0 WHERE id='default'"
        )
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)"
            " VALUES ('p1','default','AAPL',5,100,?)",
            (iso_now(),),
        )
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
            " VALUES ('t1','default','AAPL','buy',5,100,?)",
            (iso_now(),),
        )
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
            " VALUES ('s1','default',12345.0,?)",
            (iso_now(),),
        )
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, created_at)"
            " VALUES ('c1','default','user','hi',?)",
            (iso_now(),),
        )

        reset_account(conn, user_id="default")

        cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id='default'"
        ).fetchone()[0]
        assert cash == 10000.0

        for table in ("positions", "trades", "portfolio_snapshots", "chat_messages"):
            n = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id='default'"
            ).fetchone()[0]
            assert n == 0, f"{table} not cleared"

        tickers = {
            r[0] for r in conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id='default'"
            )
        }
        assert tickers == set(DEFAULT_TICKERS)


def test_reset_preserves_other_users(tmp_db):
    with get_conn(tmp_db) as conn:
        conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES ('u2', 500.0, ?)",
            (iso_now(),),
        )
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES ('w1','u2','TSLA',?)",
            (iso_now(),),
        )

        reset_account(conn, user_id="default")

        u2_cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id='u2'"
        ).fetchone()[0]
        assert u2_cash == 500.0
        u2_watch = conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE user_id='u2'"
        ).fetchone()[0]
        assert u2_watch == 1
