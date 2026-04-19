"""Chat endpoint in LLM_MOCK mode exercises trade + watchlist auto-execution."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from market.base import MarketDataProvider
from market.types import PricePoint


class FakeProvider(MarketDataProvider):
    def __init__(self, prices):
        self._prices = {k.upper(): v for k, v in prices.items()}

    async def start(self) -> None: pass
    async def stop(self) -> None: pass
    def add_ticker(self, ticker: str) -> None:
        self._prices.setdefault(ticker.upper(), 100.0)
    def remove_ticker(self, ticker: str) -> None:
        self._prices.pop(ticker.upper(), None)
    def get_price(self, ticker: str):
        t = ticker.upper()
        if t not in self._prices:
            return None
        p = self._prices[t]
        return PricePoint(ticker=t, price=p, previous_price=p,
                          timestamp=datetime.now(timezone.utc), direction="flat")
    def get_all_prices(self):
        return {t: self.get_price(t) for t in self._prices}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setenv("MASSIVE_API_KEY", "")
    import db as db_pkg
    monkeypatch.setattr(db_pkg, "DB_PATH", tmp_path / "chat.db")

    from app.main import app
    fake = FakeProvider({"AAPL": 200.0, "GOOGL": 150.0, "MSFT": 400.0, "AMZN": 180.0,
                         "TSLA": 250.0, "NVDA": 800.0, "META": 500.0, "JPM": 180.0,
                         "V": 280.0, "NFLX": 600.0})
    from app import main as main_mod
    monkeypatch.setattr(main_mod, "create_provider", lambda tickers: fake)

    with TestClient(app) as c:
        yield c


def test_chat_buy(client):
    r = client.post("/api/chat", json={"message": "buy 2 AAPL"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trades"] and body["trades"][0]["ticker"] == "AAPL"
    assert body["trades"][0]["side"] == "buy"
    # Verify position actually landed in the DB via portfolio endpoint.
    r = client.get("/api/portfolio")
    assert any(p["ticker"] == "AAPL" and p["quantity"] == 2.0 for p in r.json()["positions"])


def test_chat_add_watchlist(client):
    r = client.post("/api/chat", json={"message": "add AMD"})
    body = r.json()
    assert body["watchlist_changes"] == [{"ticker": "AMD", "action": "add"}]
    r = client.get("/api/watchlist")
    assert any(e["ticker"] == "AMD" for e in r.json()["watchlist"])


def test_chat_trade_error_surfaced(client):
    r = client.post("/api/chat", json={"message": "buy 10000 NVDA"})
    body = r.json()
    assert body["trades"] == []
    assert body["errors"] and "insufficient" in body["errors"][0].lower()


def test_chat_plain_question(client):
    r = client.post("/api/chat", json={"message": "hi"})
    body = r.json()
    assert body["message"]
    assert body["trades"] == [] and body["watchlist_changes"] == []
