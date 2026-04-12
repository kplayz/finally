# Market Simulator Design

The simulator generates realistic-looking stock price movements without any external API calls. It implements the `MarketDataProvider` interface (see `MARKET_INTERFACE.md`) and is the default when `MASSIVE_API_KEY` is not set.

---

## Price Model: Geometric Brownian Motion

Each tick, the simulator applies GBM to advance each ticker's price:

```
new_price = price * exp((drift - 0.5 * vol²) * dt + vol * sqrt(dt) * Z)
```

Where:
- `drift` — per-ticker annualized drift rate (slightly positive, ~5-15% annualized)
- `vol` — per-ticker annualized volatility (e.g., 0.30 for 30%)
- `dt` — time step in years (0.5s / 31_536_000 ≈ 1.59e-8)
- `Z` — standard normal random variable

In practice at a 500ms tick with realistic vol, each tick produces a price move of roughly ±0.05-0.15%, which looks natural.

### Why GBM

- Prices stay positive (exponential ensures no negative prices)
- Percentage moves are normally distributed (realistic)
- Simple — one formula, no hidden state
- Well-understood by finance students

---

## Seed Prices

Default prices approximate real-world levels as of early 2026:

```python
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

DEFAULT_PRICE = 100.0   # for tickers added at runtime
DEFAULT_VOL   = 0.30    # annualized, ~30%
DEFAULT_DRIFT = 0.08    # annualized, ~8%
```

Per-ticker volatility overrides for realistic feel:

```python
TICKER_VOL: dict[str, float] = {
    "TSLA": 0.55,   # high vol
    "NVDA": 0.50,   # high vol
    "AAPL": 0.22,   # lower vol, large cap
    "JPM":  0.20,
    "V":    0.18,
}
```

---

## Correlated Moves

Real stocks within a sector move together. The simulator adds a market-wide factor to all tickers each tick:

```python
MARKET_CORRELATION = 0.4   # weight of common market factor

# Each tick:
market_shock = random.gauss(0, 1)
for ticker in tickers:
    idio_shock = random.gauss(0, 1)
    Z = MARKET_CORRELATION * market_shock + sqrt(1 - MARKET_CORRELATION**2) * idio_shock
    # use Z in GBM formula
```

This ensures tickers don't drift completely independently — a broad market "up" day lifts most prices.

---

## Random Events

Every tick, each ticker has a small probability of experiencing a sudden jump (earnings surprise, news flash):

```python
EVENT_PROBABILITY = 0.0005   # ~0.05% per tick = roughly once per 30 min per ticker
EVENT_MAGNITUDE   = 0.03     # ±3% jump

# Each tick, per ticker:
if random.random() < EVENT_PROBABILITY:
    direction = random.choice([1, -1])
    price *= (1 + direction * EVENT_MAGNITUDE * random.uniform(0.5, 1.5))
```

This creates occasional dramatic moves that make the terminal feel alive.

---

## Background Task Loop

The simulator runs as a single asyncio task at ~500ms intervals:

```python
TICK_INTERVAL = 0.5  # seconds
DT = TICK_INTERVAL / 31_536_000  # fraction of year
```

Each iteration:
1. Generate market-wide shock
2. For each tracked ticker:
   a. Generate idiosyncratic shock
   b. Combine with market shock (correlation)
   c. Apply GBM formula
   d. Apply random event (if triggered)
   e. Clamp price (floor at $0.01 to prevent degenerate states)
   f. Write `PricePoint` to cache

---

## Full Implementation

```python
# backend/market/simulator.py

import asyncio
import math
import random
import threading
from datetime import datetime, timezone

from .base import MarketDataProvider
from .cache import PriceCache
from .types import PricePoint

TICK_INTERVAL = 0.5
DT = TICK_INTERVAL / 31_536_000
MARKET_CORRELATION = 0.4
CORR_COMPLEMENT = math.sqrt(1 - MARKET_CORRELATION ** 2)
EVENT_PROB = 0.0005
EVENT_MAG = 0.03

SEED_PRICES: dict[str, float] = {
    "AAPL": 192.0, "GOOGL": 178.0, "MSFT": 415.0, "AMZN": 198.0, "TSLA": 248.0,
    "NVDA": 875.0, "META": 545.0,  "JPM":  220.0, "V":    285.0, "NFLX": 635.0,
}
TICKER_VOL: dict[str, float] = {
    "TSLA": 0.55, "NVDA": 0.50, "AAPL": 0.22, "JPM": 0.20, "V": 0.18,
}
DEFAULT_PRICE = 100.0
DEFAULT_VOL   = 0.30
DEFAULT_DRIFT = 0.08


class SimulatorProvider(MarketDataProvider):
    """Generates synthetic stock prices using geometric Brownian motion."""

    def __init__(self, tickers: list[str]) -> None:
        self._cache = PriceCache()
        self._lock = threading.Lock()
        self._prices: dict[str, float] = {}
        self._task: asyncio.Task | None = None

        for ticker in tickers:
            self._init_ticker(ticker)

    def _init_ticker(self, ticker: str) -> None:
        """Set seed price and write initial cache entry."""
        ticker = ticker.upper()
        price = SEED_PRICES.get(ticker, DEFAULT_PRICE)
        self._prices[ticker] = price
        self._cache.update(PricePoint(
            ticker=ticker,
            price=price,
            previous_price=price,
            timestamp=datetime.now(timezone.utc),
            direction="flat",
        ))

    async def start(self) -> None:
        self._task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        with self._lock:
            if ticker not in self._prices:
                self._init_ticker(ticker)

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        with self._lock:
            self._prices.pop(ticker, None)
        self._cache.remove(ticker)

    def get_price(self, ticker: str) -> PricePoint | None:
        return self._cache.get(ticker.upper())

    def get_all_prices(self) -> dict[str, PricePoint]:
        return self._cache.get_all()

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            self._tick()

    def _tick(self) -> None:
        market_shock = random.gauss(0, 1)
        now = datetime.now(timezone.utc)

        with self._lock:
            tickers = list(self._prices.keys())

        for ticker in tickers:
            with self._lock:
                if ticker not in self._prices:
                    continue
                old_price = self._prices[ticker]

            vol   = TICKER_VOL.get(ticker, DEFAULT_VOL)
            drift = DEFAULT_DRIFT
            idio  = random.gauss(0, 1)
            Z     = MARKET_CORRELATION * market_shock + CORR_COMPLEMENT * idio
            log_return = (drift - 0.5 * vol ** 2) * DT + vol * math.sqrt(DT) * Z
            new_price = old_price * math.exp(log_return)

            # random event
            if random.random() < EVENT_PROB:
                direction = random.choice([1, -1])
                new_price *= 1 + direction * EVENT_MAG * random.uniform(0.5, 1.5)

            new_price = max(new_price, 0.01)

            with self._lock:
                self._prices[ticker] = new_price

            direction_str = "up" if new_price > old_price else ("down" if new_price < old_price else "flat")
            self._cache.update(PricePoint(
                ticker=ticker,
                price=round(new_price, 4),
                previous_price=round(old_price, 4),
                timestamp=now,
                direction=direction_str,
            ))
```

---

## Properties of the Simulation

| Property | Value |
|---|---|
| Update interval | 500ms |
| Typical tick move | ±0.05–0.15% (varies by vol) |
| Market correlation | 40% common factor |
| Random event rate | ~once per 30 min per ticker |
| Random event size | 1.5–4.5% jump |
| Price floor | $0.01 |
| Supported tickers | Any string — no validation |

---

## Dynamic Ticker Handling

When the user adds a new ticker:
- `add_ticker(ticker)` is called on the running provider
- The ticker is initialized with `DEFAULT_PRICE = $100.00` if not in `SEED_PRICES`
- The simulator begins generating prices immediately on the next tick
- Any ticker string is accepted — useful for demo purposes

When a ticker is removed:
- `remove_ticker(ticker)` removes it from `_prices` and evicts it from the cache
- Subsequent SSE frames will not include it
- If the ticker is re-added later, it restarts from the default seed price

---

## Testing

The simulator's behavior can be verified by:

1. **Price stays positive** — run 10,000 ticks with very high vol, assert all prices > 0
2. **Approximate drift** — run many ticks, assert geometric mean return is near the drift rate
3. **Correlation** — run two tickers, compute correlation of their log returns, assert ~40%
4. **Event injection** — temporarily set `EVENT_PROB = 1.0`, verify each tick produces a jump

Unit tests live in `backend/tests/test_simulator.py`.
