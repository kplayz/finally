"""Geometric Brownian Motion price simulator.

Implements MarketDataProvider without any external API calls.
This is the default provider when MASSIVE_API_KEY is not set.
"""

import asyncio
import math
import random
import threading
from datetime import datetime, timezone

from .base import MarketDataProvider
from .cache import PriceCache
from .types import PricePoint

# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------

TICK_INTERVAL: float = 0.5  # seconds between price updates
DT: float = TICK_INTERVAL / 31_536_000  # tick as a fraction of a year

# ---------------------------------------------------------------------------
# GBM / correlation constants
# ---------------------------------------------------------------------------

DEFAULT_DRIFT: float = 0.08  # 8 % annualised drift
DEFAULT_VOL: float = 0.30    # 30 % annualised volatility
DEFAULT_PRICE: float = 100.0  # seed price for unknown tickers

MARKET_CORRELATION: float = 0.40
CORR_COMPLEMENT: float = math.sqrt(1 - MARKET_CORRELATION ** 2)

# ---------------------------------------------------------------------------
# Random-event constants
# ---------------------------------------------------------------------------

EVENT_PROB: float = 0.0005   # ~0.05 % per tick  ≈ once / 30 min per ticker
EVENT_MAG: float = 0.03      # base ±3 % jump

# ---------------------------------------------------------------------------
# Per-ticker seed prices (approximate real-world levels, early 2026)
# ---------------------------------------------------------------------------

SEED_PRICES: dict[str, float] = {
    "AAPL":  192.0,
    "GOOGL": 178.0,
    "MSFT":  415.0,
    "AMZN":  198.0,
    "TSLA":  248.0,
    "NVDA":  875.0,
    "META":  545.0,
    "JPM":   220.0,
    "V":     285.0,
    "NFLX":  635.0,
}

# Per-ticker annualised volatility overrides
TICKER_VOL: dict[str, float] = {
    "TSLA": 0.55,
    "NVDA": 0.50,
    "AAPL": 0.22,
    "JPM":  0.20,
    "V":    0.18,
}


class SimulatorProvider(MarketDataProvider):
    """Generates synthetic stock prices using geometric Brownian motion.

    Runs as an asyncio background task at ~500 ms intervals.  All ticker
    strings are accepted; unknown tickers start at DEFAULT_PRICE.

    Thread-safety: ``_prices`` is guarded by ``_lock`` so that
    ``add_ticker`` / ``remove_ticker`` calls from route handlers (which
    may run in a threadpool) are safe while ``_tick`` is executing.
    """

    def __init__(self, tickers: list[str]) -> None:
        self._cache = PriceCache()
        self._lock = threading.Lock()
        self._prices: dict[str, float] = {}
        self._task: asyncio.Task | None = None

        for ticker in tickers:
            self._init_ticker(ticker)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _init_ticker(self, ticker: str) -> None:
        """Seed *ticker* with its initial price and write a flat PricePoint."""
        ticker = ticker.upper()
        price = SEED_PRICES.get(ticker, DEFAULT_PRICE)
        self._prices[ticker] = price
        self._cache.update(
            PricePoint(
                ticker=ticker,
                price=price,
                previous_price=price,
                timestamp=datetime.now(timezone.utc),
                direction="flat",
            )
        )

    # ------------------------------------------------------------------
    # MarketDataProvider interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the GBM tick loop as an asyncio background task."""
        self._task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        """Cancel the tick loop and wait for it to finish."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def add_ticker(self, ticker: str) -> None:
        """Add *ticker* to the simulation (no-op if already tracked)."""
        ticker = ticker.upper()
        with self._lock:
            if ticker not in self._prices:
                self._init_ticker(ticker)

    def remove_ticker(self, ticker: str) -> None:
        """Remove *ticker* from the simulation and evict it from the cache."""
        ticker = ticker.upper()
        with self._lock:
            self._prices.pop(ticker, None)
        self._cache.remove(ticker)

    def get_price(self, ticker: str) -> PricePoint | None:
        return self._cache.get(ticker.upper())

    def get_all_prices(self) -> dict[str, PricePoint]:
        return self._cache.get_all()

    # ------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            self._tick()

    def _tick(self) -> None:
        """Advance all tracked tickers by one GBM step."""
        market_shock = random.gauss(0, 1)
        now = datetime.now(timezone.utc)

        with self._lock:
            tickers = list(self._prices.keys())

        for ticker in tickers:
            with self._lock:
                if ticker not in self._prices:
                    # ticker was removed while we were iterating
                    continue
                old_price = self._prices[ticker]

            vol = TICKER_VOL.get(ticker, DEFAULT_VOL)
            idio_shock = random.gauss(0, 1)
            Z = MARKET_CORRELATION * market_shock + CORR_COMPLEMENT * idio_shock
            log_return = (DEFAULT_DRIFT - 0.5 * vol ** 2) * DT + vol * math.sqrt(DT) * Z
            new_price = old_price * math.exp(log_return)

            # Random event: occasional sudden jump
            if random.random() < EVENT_PROB:
                sign = random.choice([1, -1])
                new_price *= 1.0 + sign * EVENT_MAG * random.uniform(0.5, 1.5)

            # Price floor — prevents degenerate near-zero states
            new_price = max(new_price, 0.01)

            with self._lock:
                self._prices[ticker] = new_price

            direction = (
                "up"   if new_price > old_price else
                "down" if new_price < old_price else
                "flat"
            )
            self._cache.update(
                PricePoint(
                    ticker=ticker,
                    price=round(new_price, 4),
                    previous_price=round(old_price, 4),
                    timestamp=now,
                    direction=direction,
                )
            )
