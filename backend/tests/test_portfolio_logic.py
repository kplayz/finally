"""Pure-function tests for portfolio.execute_trade (no FastAPI)."""

from __future__ import annotations

import pytest

from app.portfolio import TradeError, execute_trade, get_cash, get_position
from db import get_conn, init_db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "pf.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    import db as db_pkg
    monkeypatch.setattr(db_pkg, "DB_PATH", path)
    init_db(path)
    with get_conn(path) as c:
        yield c


def test_buy_updates_cash_and_position(conn):
    res = execute_trade(conn, user_id="default", ticker="AAPL", side="buy",
                       quantity=2, price=100.0)
    assert res.total_cost == 200.0
    assert res.cash_remaining == 9800.0
    qty, avg = get_position(conn, "default", "AAPL")
    assert qty == 2.0 and avg == 100.0


def test_buy_weighted_average_cost(conn):
    execute_trade(conn, user_id="default", ticker="AAPL", side="buy", quantity=2, price=100.0)
    execute_trade(conn, user_id="default", ticker="AAPL", side="buy", quantity=3, price=120.0)
    qty, avg = get_position(conn, "default", "AAPL")
    assert qty == 5.0
    assert avg == pytest.approx((2 * 100 + 3 * 120) / 5)


def test_sell_reduces_and_credits(conn):
    execute_trade(conn, user_id="default", ticker="AAPL", side="buy", quantity=4, price=100.0)
    res = execute_trade(conn, user_id="default", ticker="AAPL", side="sell", quantity=1, price=110.0)
    assert res.cash_remaining == pytest.approx(9600.0 + 110.0)
    qty, _ = get_position(conn, "default", "AAPL")
    assert qty == 3.0


def test_sell_all_deletes_position(conn):
    execute_trade(conn, user_id="default", ticker="AAPL", side="buy", quantity=1, price=100.0)
    execute_trade(conn, user_id="default", ticker="AAPL", side="sell", quantity=1, price=100.0)
    assert get_position(conn, "default", "AAPL") is None


def test_insufficient_cash_rejected(conn):
    with pytest.raises(TradeError, match="insufficient"):
        execute_trade(conn, user_id="default", ticker="AAPL", side="buy", quantity=1000, price=100.0)
    # Cash unchanged
    assert get_cash(conn, "default") == 10000.0


def test_sell_more_than_held_rejected(conn):
    execute_trade(conn, user_id="default", ticker="AAPL", side="buy", quantity=1, price=100.0)
    with pytest.raises(TradeError, match="only"):
        execute_trade(conn, user_id="default", ticker="AAPL", side="sell", quantity=2, price=100.0)


def test_sell_nonexistent_rejected(conn):
    with pytest.raises(TradeError, match="no position"):
        execute_trade(conn, user_id="default", ticker="TSLA", side="sell", quantity=1, price=100.0)


def test_fractional_shares(conn):
    res = execute_trade(conn, user_id="default", ticker="AMZN", side="buy",
                       quantity=0.5, price=200.0)
    assert res.cash_remaining == pytest.approx(9900.0)
    qty, _ = get_position(conn, "default", "AMZN")
    assert qty == 0.5
