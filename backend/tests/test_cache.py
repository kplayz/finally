"""Unit tests for PriceCache."""

from datetime import datetime, timezone

import pytest

from market.cache import PriceCache
from market.types import PricePoint


def _make_point(ticker: str, price: float, prev: float | None = None) -> PricePoint:
    return PricePoint(
        ticker=ticker,
        price=price,
        previous_price=prev if prev is not None else price,
        timestamp=datetime.now(timezone.utc),
        direction="flat",
    )


class TestPriceCache:
    def test_get_missing_returns_none(self):
        cache = PriceCache()
        assert cache.get("AAPL") is None

    def test_update_and_get(self):
        cache = PriceCache()
        point = _make_point("AAPL", 192.0)
        cache.update(point)
        result = cache.get("AAPL")
        assert result is not None
        assert result.price == 192.0
        assert result.ticker == "AAPL"

    def test_update_overwrites_previous(self):
        cache = PriceCache()
        cache.update(_make_point("AAPL", 100.0))
        cache.update(_make_point("AAPL", 200.0))
        assert cache.get("AAPL").price == 200.0

    def test_get_all_returns_copy(self):
        cache = PriceCache()
        cache.update(_make_point("AAPL", 192.0))
        cache.update(_make_point("MSFT", 415.0))
        all_prices = cache.get_all()
        assert set(all_prices.keys()) == {"AAPL", "MSFT"}
        # Modifying the returned dict must not affect the cache
        all_prices["AAPL"] = None  # type: ignore[assignment]
        assert cache.get("AAPL") is not None

    def test_remove_evicts_ticker(self):
        cache = PriceCache()
        cache.update(_make_point("AAPL", 192.0))
        cache.remove("AAPL")
        assert cache.get("AAPL") is None

    def test_remove_missing_ticker_is_noop(self):
        cache = PriceCache()
        cache.remove("ZZZZ")  # must not raise

    def test_clear_empties_cache(self):
        cache = PriceCache()
        cache.update(_make_point("AAPL", 192.0))
        cache.update(_make_point("MSFT", 415.0))
        cache.clear()
        assert len(cache) == 0
        assert cache.get_all() == {}

    def test_len(self):
        cache = PriceCache()
        assert len(cache) == 0
        cache.update(_make_point("AAPL", 100.0))
        assert len(cache) == 1
        cache.update(_make_point("TSLA", 248.0))
        assert len(cache) == 2
        cache.remove("AAPL")
        assert len(cache) == 1
