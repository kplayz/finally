"""Unit tests for MassiveProvider.

Uses `respx` to mock httpx calls so no real network requests are made.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from market.massive import BASE_URL, POLL_INTERVAL, MassiveProvider
from market.types import PricePoint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider():
    return MassiveProvider(api_key="test-key", tickers=["AAPL", "MSFT"])


def _snapshot_response(tickers_data: list[dict]) -> dict:
    """Build a fake Massive multi-ticker snapshot JSON body."""
    return {
        "count": len(tickers_data),
        "status": "OK",
        "tickers": tickers_data,
    }


def _ticker_item(ticker: str, price: float) -> dict:
    return {
        "ticker": ticker,
        "todaysChangePerc": 0.5,
        "lastTrade": {"p": price, "s": 100, "t": 1617901342969834000},
        "prevDay": {"c": price - 1.0},
    }


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_initial_tickers_stored_uppercase(self):
        p = MassiveProvider(api_key="k", tickers=["aapl", "msft"])
        assert "AAPL" in p._tickers
        assert "MSFT" in p._tickers

    def test_cache_empty_on_init(self):
        p = MassiveProvider(api_key="k", tickers=["AAPL"])
        assert p.get_price("AAPL") is None


# ---------------------------------------------------------------------------
# add_ticker / remove_ticker
# ---------------------------------------------------------------------------


class TestTickerManagement:
    def test_add_ticker(self, provider):
        provider.add_ticker("TSLA")
        assert "TSLA" in provider._tickers

    def test_add_ticker_uppercased(self, provider):
        provider.add_ticker("tsla")
        assert "TSLA" in provider._tickers

    def test_remove_ticker(self, provider):
        provider.remove_ticker("AAPL")
        assert "AAPL" not in provider._tickers

    def test_remove_ticker_evicts_cache(self, provider):
        # Manually seed cache
        provider._cache.update(
            PricePoint("AAPL", 192.0, 192.0, datetime.now(timezone.utc), "flat")
        )
        provider.remove_ticker("AAPL")
        assert provider.get_price("AAPL") is None

    def test_remove_missing_ticker_is_noop(self, provider):
        provider.remove_ticker("ZZZZ")  # must not raise


# ---------------------------------------------------------------------------
# _fetch_and_update
# ---------------------------------------------------------------------------


class TestFetchAndUpdate:
    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_fetch_updates_cache(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(
            return_value=httpx.Response(
                200,
                json=_snapshot_response(
                    [_ticker_item("AAPL", 192.0), _ticker_item("MSFT", 415.0)]
                ),
            )
        )
        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)

        aapl = provider.get_price("AAPL")
        msft = provider.get_price("MSFT")
        assert aapl is not None and aapl.price == 192.0
        assert msft is not None and msft.price == 415.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_direction_up(self, provider):
        # Seed a lower price first
        provider._cache.update(
            PricePoint("AAPL", 190.0, 190.0, datetime.now(timezone.utc), "flat")
        )
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(
            return_value=httpx.Response(
                200,
                json=_snapshot_response([_ticker_item("AAPL", 192.0)]),
            )
        )
        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)

        assert provider.get_price("AAPL").direction == "up"

    @pytest.mark.asyncio
    @respx.mock
    async def test_direction_down(self, provider):
        provider._cache.update(
            PricePoint("AAPL", 195.0, 195.0, datetime.now(timezone.utc), "flat")
        )
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(
            return_value=httpx.Response(
                200,
                json=_snapshot_response([_ticker_item("AAPL", 192.0)]),
            )
        )
        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)

        assert provider.get_price("AAPL").direction == "down"

    @pytest.mark.asyncio
    @respx.mock
    async def test_direction_flat_on_first_seen(self, provider):
        """First observation has no previous price → direction is flat."""
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(
            return_value=httpx.Response(
                200,
                json=_snapshot_response([_ticker_item("AAPL", 192.0)]),
            )
        )
        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)

        assert provider.get_price("AAPL").direction == "flat"

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_swallowed(self, provider):
        """A network error must not propagate; cache stays intact."""
        provider._cache.update(
            PricePoint("AAPL", 190.0, 190.0, datetime.now(timezone.utc), "flat")
        )
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(side_effect=httpx.ConnectError("timeout"))

        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)  # must not raise

        # Cache must still have the old price
        assert provider.get_price("AAPL").price == 190.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_swallowed(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(return_value=httpx.Response(500, json={"error": "internal"}))

        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)  # must not raise

    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_last_trade_skipped(self, provider):
        """Ticker items without lastTrade must be silently skipped."""
        item_no_trade = {"ticker": "AAPL", "todaysChangePerc": 0.5}
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
        ).mock(
            return_value=httpx.Response(
                200,
                json=_snapshot_response([item_no_trade]),
            )
        )
        async with httpx.AsyncClient() as client:
            await provider._fetch_and_update(client)

        assert provider.get_price("AAPL") is None  # was not updated


# ---------------------------------------------------------------------------
# validate_ticker
# ---------------------------------------------------------------------------


class TestEmptyTickerSet:
    @pytest.mark.asyncio
    async def test_poll_loop_skips_fetch_with_no_tickers(self):
        """When the ticker set is empty, the poll loop must not call _fetch_and_update."""
        provider = MassiveProvider(api_key="test-key", tickers=[])
        fetch_called = False

        async def fake_fetch(client):
            nonlocal fetch_called
            fetch_called = True

        provider._fetch_and_update = fake_fetch  # type: ignore[method-assign]

        await provider.start()
        await asyncio.sleep(0.05)
        await provider.stop()

        assert fetch_called is False, "_fetch_and_update should not be called with empty tickers"


class TestValidateTicker:
    @pytest.mark.asyncio
    @respx.mock
    async def test_valid_ticker_returns_true(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"status": "OK", "ticker": {"ticker": "AAPL"}},
            )
        )
        result = await provider.validate_ticker("AAPL")
        assert result is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_invalid_ticker_404_returns_false(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/ZZZZ"
        ).mock(return_value=httpx.Response(404, json={}))
        result = await provider.validate_ticker("ZZZZ")
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_returns_false(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
        ).mock(side_effect=httpx.ConnectError("timeout"))
        result = await provider.validate_ticker("AAPL")
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_auth_error_returns_false(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
        ).mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
        result = await provider.validate_ticker("AAPL")
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_rate_limit_returns_false(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
        ).mock(return_value=httpx.Response(429, json={"error": "rate limited"}))
        result = await provider.validate_ticker("AAPL")
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_lowercase_ticker_uppercased(self, provider):
        respx.get(
            f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"status": "OK", "ticker": {"ticker": "AAPL"}},
            )
        )
        result = await provider.validate_ticker("aapl")
        assert result is True


# ---------------------------------------------------------------------------
# Async start / stop
# ---------------------------------------------------------------------------


class TestAsyncLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, provider):
        assert provider._task is None
        await provider.start()
        assert provider._task is not None
        assert not provider._task.done()
        await provider.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, provider):
        await provider.start()
        await provider.stop()
        assert provider._task is None

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, provider):
        await provider.start()
        await provider.stop()
        await provider.stop()  # second call must not raise

    @pytest.mark.asyncio
    async def test_poll_loop_calls_fetch(self, provider):
        """The poll loop should call _fetch_and_update on its first iteration."""
        called = False

        async def fake_fetch(client):
            nonlocal called
            called = True

        # Replace instance method — takes priority over class method lookup
        provider._fetch_and_update = fake_fetch  # type: ignore[method-assign]

        await provider.start()
        # The poll loop fetches immediately before sleeping, so a brief yield
        # is enough to confirm it ran.
        await asyncio.sleep(0.05)
        await provider.stop()

        assert called is True, "_fetch_and_update was not called on first iteration"
        assert provider._task is None  # stopped cleanly
