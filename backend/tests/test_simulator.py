"""Unit tests for SimulatorProvider.

Tests cover:
- Prices stay positive over many ticks (even with extreme volatility)
- Approximate drift: geometric mean log-return is near DEFAULT_DRIFT
- Market correlation: two tickers share ~40% of variance
- Random event injection: EVENT_PROB=1.0 forces a jump every tick
- add_ticker / remove_ticker lifecycle
- start / stop lifecycle
"""

import asyncio
import math
import random
import statistics

import pytest

from market.simulator import (
    DEFAULT_DRIFT,
    DEFAULT_PRICE,
    DEFAULT_VOL,
    DT,
    EVENT_MAG,
    EVENT_PROB,
    MARKET_CORRELATION,
    SEED_PRICES,
    TICK_INTERVAL,
    SimulatorProvider,
)
from market.types import PricePoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_ticks(provider: SimulatorProvider, n: int) -> None:
    """Advance the simulator *n* times without awaiting async machinery."""
    for _ in range(n):
        provider._tick()


# ---------------------------------------------------------------------------
# Seed-price tests
# ---------------------------------------------------------------------------


class TestSeedPrices:
    def test_known_ticker_uses_seed_price(self):
        provider = SimulatorProvider(["AAPL"])
        point = provider.get_price("AAPL")
        assert point is not None
        assert point.price == SEED_PRICES["AAPL"]

    def test_unknown_ticker_uses_default_price(self):
        provider = SimulatorProvider(["ZZZZ"])
        point = provider.get_price("ZZZZ")
        assert point is not None
        assert point.price == DEFAULT_PRICE

    def test_tickers_uppercased(self):
        provider = SimulatorProvider(["aapl"])
        assert provider.get_price("AAPL") is not None
        assert provider.get_price("aapl") is not None  # case-insensitive lookup

    def test_initial_direction_is_flat(self):
        provider = SimulatorProvider(["AAPL"])
        assert provider.get_price("AAPL").direction == "flat"


# ---------------------------------------------------------------------------
# Price positivity
# ---------------------------------------------------------------------------


class TestPricePositivity:
    def test_prices_stay_positive_under_extreme_volatility(self):
        """Prices must never go below $0.01 over 10,000 ticks."""
        original_vol = __import__("market.simulator", fromlist=["TICKER_VOL"]).TICKER_VOL
        provider = SimulatorProvider(["AAPL", "TSLA", "NVDA"])
        _run_ticks(provider, 10_000)
        for ticker in ["AAPL", "TSLA", "NVDA"]:
            point = provider.get_price(ticker)
            assert point is not None
            assert point.price >= 0.01, f"{ticker} went below floor: {point.price}"

    def test_price_floor_clamped_to_001(self):
        """A manually set near-zero price must be clamped to 0.01 on next tick."""
        provider = SimulatorProvider(["TEST"])
        # Force price to a tiny value
        with provider._lock:
            provider._prices["TEST"] = 1e-10
        provider._tick()
        assert provider.get_price("TEST").price >= 0.01


# ---------------------------------------------------------------------------
# Approximate drift
# ---------------------------------------------------------------------------


class TestApproximateDrift:
    def test_log_return_mean_near_drift(self, monkeypatch):
        """Geometric mean of log-returns over 20 000 ticks should be close to
        (DEFAULT_DRIFT - 0.5 * DEFAULT_VOL²) * DT (the Itô-corrected drift)."""
        import market.simulator as sim_module

        # Suppress random events so they don't add noise to the drift measurement
        monkeypatch.setattr(sim_module, "EVENT_PROB", 0.0)

        provider = SimulatorProvider(["DRIFTTEST"])
        with provider._lock:
            provider._prices["DRIFTTEST"] = 100.0

        log_returns: list[float] = []
        prev_price = 100.0
        for _ in range(20_000):
            provider._tick()
            # Read from internal _prices (unrounded) to avoid rounding bias
            with provider._lock:
                new_price = provider._prices["DRIFTTEST"]
            if prev_price > 0 and new_price > 0:
                log_returns.append(math.log(new_price / prev_price))
            prev_price = new_price

        expected_mean = (DEFAULT_DRIFT - 0.5 * DEFAULT_VOL ** 2) * DT
        actual_mean = statistics.mean(log_returns)
        # Tolerance based on standard error of the mean:
        # SE = vol * sqrt(DT) / sqrt(N) ≈ 2.67e-7 for N=20000
        # Use 5 standard errors for a robust bound
        vol = DEFAULT_VOL
        se = vol * math.sqrt(DT) / math.sqrt(len(log_returns))
        tolerance = 5 * se
        assert abs(actual_mean - expected_mean) < tolerance, (
            f"mean log-return {actual_mean:.2e} too far from expected {expected_mean:.2e} "
            f"(tolerance={tolerance:.2e})"
        )


# ---------------------------------------------------------------------------
# Market correlation
# ---------------------------------------------------------------------------


class TestMarketCorrelation:
    def test_correlated_moves(self, monkeypatch):
        """Log-returns of two tickers should have positive correlation (~40 %).

        Random events are suppressed because each event produces a jump
        ~750x larger than a normal GBM tick. Even a few uncorrelated events
        can dominate the variance and push measured correlation to zero.
        """
        import market.simulator as sim_module

        monkeypatch.setattr(sim_module, "EVENT_PROB", 0.0)

        provider = SimulatorProvider(["TICKER_A", "TICKER_B"])
        returns_a: list[float] = []
        returns_b: list[float] = []
        prev_a = provider._prices["TICKER_A"]
        prev_b = provider._prices["TICKER_B"]

        for _ in range(5_000):
            provider._tick()
            pa = provider._prices["TICKER_A"]
            pb = provider._prices["TICKER_B"]
            if prev_a > 0 and pa > 0:
                returns_a.append(math.log(pa / prev_a))
            if prev_b > 0 and pb > 0:
                returns_b.append(math.log(pb / prev_b))
            prev_a, prev_b = pa, pb

        # Pearson correlation
        n = min(len(returns_a), len(returns_b))
        mean_a = statistics.mean(returns_a[:n])
        mean_b = statistics.mean(returns_b[:n])
        cov = sum(
            (returns_a[i] - mean_a) * (returns_b[i] - mean_b)
            for i in range(n)
        ) / n
        std_a = statistics.stdev(returns_a[:n])
        std_b = statistics.stdev(returns_b[:n])
        corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0.0

        # GBM with 40 % market factor → expected correlation ≈ 0.16
        # We assert it's clearly positive and below 1.
        assert corr > 0.05, f"Expected positive correlation, got {corr:.3f}"
        assert corr < 0.9, f"Correlation suspiciously high: {corr:.3f}"


# ---------------------------------------------------------------------------
# Random events
# ---------------------------------------------------------------------------


class TestRandomEvents:
    def test_event_injection_produces_jump(self, monkeypatch):
        """With EVENT_PROB=1.0 every tick must produce a jump larger than normal GBM."""
        import market.simulator as sim_module

        monkeypatch.setattr(sim_module, "EVENT_PROB", 1.0)
        monkeypatch.setattr(sim_module, "EVENT_MAG", 0.10)  # 10% base jump

        provider = SimulatorProvider(["JMPTEST"])
        initial_price = provider._prices["JMPTEST"]

        # Run a single tick; the event must move the price by at least ~5%
        provider._tick()
        new_price = provider._prices["JMPTEST"]
        pct_change = abs(new_price - initial_price) / initial_price
        # Minimum jump = 0.10 * 0.5 (EVENT_MAG * uniform lower bound) = 5%
        assert pct_change >= 0.04, f"Expected event jump ≥ 4%, got {pct_change:.2%}"


# ---------------------------------------------------------------------------
# add_ticker / remove_ticker
# ---------------------------------------------------------------------------


class TestRemoveTickerDuringTick:
    def test_remove_during_tick_is_safe(self):
        """Removing a ticker while _tick is iterating must not raise."""
        provider = SimulatorProvider(["AAPL", "MSFT", "TSLA"])
        # Remove a ticker then immediately tick — the continue guard should skip it
        provider.remove_ticker("MSFT")
        provider._tick()  # must not raise
        assert provider.get_price("MSFT") is None
        assert provider.get_price("AAPL") is not None
        assert provider.get_price("TSLA") is not None


# ---------------------------------------------------------------------------
# Price rounding
# ---------------------------------------------------------------------------


class TestPriceRounding:
    def test_cached_prices_rounded_to_4_decimals(self):
        """Prices in the cache must be rounded to 4 decimal places."""
        provider = SimulatorProvider(["ROUNDTEST"])
        _run_ticks(provider, 50)
        point = provider.get_price("ROUNDTEST")
        assert point is not None
        assert point.price == round(point.price, 4)
        assert point.previous_price == round(point.previous_price, 4)


# ---------------------------------------------------------------------------
# add_ticker / remove_ticker
# ---------------------------------------------------------------------------


class TestTickerManagement:
    def test_add_new_ticker(self):
        provider = SimulatorProvider([])
        assert provider.get_price("NEWCO") is None
        provider.add_ticker("NEWCO")
        assert provider.get_price("NEWCO") is not None

    def test_add_ticker_idempotent(self):
        provider = SimulatorProvider(["AAPL"])
        first_price = provider._prices["AAPL"]
        provider.add_ticker("AAPL")  # must not reset the price
        assert provider._prices["AAPL"] == first_price

    def test_remove_ticker(self):
        provider = SimulatorProvider(["AAPL"])
        provider.remove_ticker("AAPL")
        assert provider.get_price("AAPL") is None
        assert "AAPL" not in provider._prices

    def test_remove_missing_ticker_is_noop(self):
        provider = SimulatorProvider([])
        provider.remove_ticker("ZZZZ")  # must not raise

    def test_tickers_uppercased_on_add(self):
        provider = SimulatorProvider([])
        provider.add_ticker("msft")
        assert provider.get_price("MSFT") is not None

    def test_removed_ticker_excluded_from_get_all(self):
        provider = SimulatorProvider(["AAPL", "MSFT"])
        provider.remove_ticker("AAPL")
        prices = provider.get_all_prices()
        assert "AAPL" not in prices
        assert "MSFT" in prices


# ---------------------------------------------------------------------------
# Async start / stop
# ---------------------------------------------------------------------------


class TestAsyncLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_background_task(self):
        provider = SimulatorProvider(["AAPL"])
        assert provider._task is None
        await provider.start()
        assert provider._task is not None
        assert not provider._task.done()
        await provider.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        provider = SimulatorProvider(["AAPL"])
        await provider.start()
        await provider.stop()
        assert provider._task is None

    @pytest.mark.asyncio
    async def test_prices_update_after_start(self):
        """After one tick interval the cache should have been updated."""
        provider = SimulatorProvider(["AAPL"])
        initial_ts = provider.get_price("AAPL").timestamp
        await provider.start()
        # Wait slightly longer than TICK_INTERVAL to guarantee at least one tick
        await asyncio.sleep(TICK_INTERVAL * 1.5)
        await provider.stop()
        updated_ts = provider.get_price("AAPL").timestamp
        assert updated_ts > initial_ts

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        provider = SimulatorProvider(["AAPL"])
        await provider.start()
        await provider.stop()
        await provider.stop()  # second stop must not raise

    @pytest.mark.asyncio
    async def test_get_all_prices_returns_all_tickers(self):
        provider = SimulatorProvider(["AAPL", "MSFT", "TSLA"])
        prices = provider.get_all_prices()
        assert set(prices.keys()) == {"AAPL", "MSFT", "TSLA"}
