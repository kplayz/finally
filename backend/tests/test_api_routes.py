"""Integration tests for FastAPI routes using a fake market provider."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from market.base import MarketDataProvider
from market.types import PricePoint


class FakeProvider(MarketDataProvider):
    def __init__(self, prices: dict[str, float]):
        self._prices: dict[str, float] = {k.upper(): v for k, v in prices.items()}

    async def start(self) -> None: pass
    async def stop(self) -> None: pass

    def add_ticker(self, ticker: str) -> None:
        self._prices.setdefault(ticker.upper(), 100.0)

    def remove_ticker(self, ticker: str) -> None:
        self._prices.pop(ticker.upper(), None)

    def get_price(self, ticker: str) -> PricePoint | None:
        t = ticker.upper()
        if t not in self._prices:
            return None
        p = self._prices[t]
        return PricePoint(ticker=t, price=p, previous_price=p, timestamp=datetime.now(timezone.utc), direction="flat")

    def get_all_prices(self) -> dict[str, PricePoint]:
        return {t: self.get_price(t) for t in self._prices}  # type: ignore[misc]

    def set_price(self, ticker: str, price: float) -> None:
        self._prices[ticker.upper()] = price


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / "routes.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_path))
    monkeypatch.setenv("LLM_MOCK", "true")
    # Prevent lifespan from spinning the real simulator.
    monkeypatch.setenv("MASSIVE_API_KEY", "")

    import db as db_pkg
    monkeypatch.setattr(db_pkg, "DB_PATH", db_path)

    # Import app after env is set.
    from app.main import app
    # Override the market provider via lifespan patching.
    fake = FakeProvider({
        "AAPL": 200.0, "GOOGL": 150.0, "MSFT": 400.0, "AMZN": 180.0,
        "TSLA": 250.0, "NVDA": 800.0, "META": 500.0, "JPM": 180.0,
        "V": 280.0, "NFLX": 600.0,
    })

    # Monkey-patch create_provider to return our fake.
    from market import factory as factory_mod
    monkeypatch.setattr(factory_mod, "create_provider", lambda tickers: fake)
    import market as market_mod
    monkeypatch.setattr(market_mod, "create_provider", lambda tickers: fake)
    from app import main as main_mod
    monkeypatch.setattr(main_mod, "create_provider", lambda tickers: fake)

    with TestClient(app) as client:
        client.app.state._fake_provider = fake  # so tests can mutate prices
        yield client


def test_health(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_default_watchlist_and_portfolio(app_client):
    r = app_client.get("/api/watchlist")
    assert r.status_code == 200
    tickers = [e["ticker"] for e in r.json()["watchlist"]]
    assert "AAPL" in tickers and len(tickers) == 10

    r = app_client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["cash_balance"] == 10000.0
    assert body["total_value"] == 10000.0
    assert body["positions"] == []


def test_add_remove_watchlist(app_client):
    r = app_client.post("/api/watchlist", json={"ticker": "amd"})
    assert r.status_code == 200
    tickers = [e["ticker"] for e in r.json()["watchlist"]]
    assert "AMD" in tickers

    r = app_client.delete("/api/watchlist/AMD")
    assert r.status_code == 200
    tickers = [e["ticker"] for e in r.json()["watchlist"]]
    assert "AMD" not in tickers

    r = app_client.delete("/api/watchlist/DOESNOTEXIST")
    assert r.status_code == 404


def test_buy_and_sell_roundtrip(app_client):
    r = app_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "buy"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_cost"] == 400.0
    assert body["cash_remaining"] == 9600.0

    r = app_client.get("/api/portfolio")
    pos = r.json()["positions"]
    assert len(pos) == 1 and pos[0]["ticker"] == "AAPL" and pos[0]["quantity"] == 2.0

    # Move the price up and sell — cash should reflect the higher price.
    app_client.app.state._fake_provider.set_price("AAPL", 220.0)
    r = app_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "sell"})
    assert r.status_code == 200
    assert r.json()["cash_remaining"] == 9600.0 + 2 * 220.0


def test_insufficient_cash_returns_400(app_client):
    r = app_client.post("/api/portfolio/trade", json={"ticker": "NVDA", "quantity": 1000, "side": "buy"})
    assert r.status_code == 400
    assert "insufficient" in r.json()["detail"].lower()


def test_history_records_snapshot_after_trade(app_client):
    app_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    r = app_client.get("/api/portfolio/history")
    assert r.status_code == 200
    assert len(r.json()["snapshots"]) >= 1


def test_reset_returns_to_seed(app_client):
    app_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    r = app_client.post("/api/reset")
    assert r.status_code == 200
    r = app_client.get("/api/portfolio")
    assert r.json()["cash_balance"] == 10000.0
    assert r.json()["positions"] == []
