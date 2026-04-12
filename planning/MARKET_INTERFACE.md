# Market Data Interface Design

## Overview

The market data layer provides a unified interface for retrieving stock prices. Two implementations exist behind a common abstract base:

- **`SimulatorProvider`** — geometric Brownian motion simulation, no external dependencies
- **`MassiveProvider`** — polls the Massive REST API (formerly Polygon.io)

Selection is automatic: if `MASSIVE_API_KEY` is set and non-empty, the Massive provider is used; otherwise the simulator runs.

---

## Architecture

```
┌─────────────────────────────────────────┐
│          MarketDataProvider (ABC)        │
│  + start() / stop()                     │
│  + add_ticker(ticker) / remove_ticker() │
│  + get_price(ticker) -> PricePoint      │
│  + get_all_prices() -> dict             │
└────────────┬────────────────────────────┘
             │ implements
    ┌─────────┴──────────┐
    │                    │
SimulatorProvider    MassiveProvider
(background task:    (background task:
 ~500ms GBM loop)    15s REST poll)
    │                    │
    └────────┬───────────┘
             │ writes to
         PriceCache
         (in-memory dict, thread-safe)
             │ read by
         SSE stream handler
```

All downstream code (SSE streaming, API routes, portfolio valuation) reads from `PriceCache`. It never knows which provider is running.

---

## Data Structures

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PricePoint:
    ticker: str
    price: float
    previous_price: float
    timestamp: datetime
    direction: str  # "up", "down", or "flat"
```

---

## Abstract Interface

```python
# backend/market/base.py

from abc import ABC, abstractmethod
from .types import PricePoint


class MarketDataProvider(ABC):
    """Common interface for all market data sources."""

    @abstractmethod
    async def start(self) -> None:
        """Start the background data collection task."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task gracefully."""

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Begin tracking a new ticker."""

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker."""

    @abstractmethod
    def get_price(self, ticker: str) -> PricePoint | None:
        """Return the latest PricePoint for a ticker, or None if not tracked."""

    @abstractmethod
    def get_all_prices(self) -> dict[str, PricePoint]:
        """Return the latest PricePoint for every tracked ticker."""
```

---

## Price Cache

A thin thread-safe wrapper around a dict. Both providers write here; all readers access it directly.

```python
# backend/market/cache.py

import threading
from .types import PricePoint


class PriceCache:
    """Thread-safe in-memory price store."""

    def __init__(self) -> None:
        self._data: dict[str, PricePoint] = {}
        self._lock = threading.Lock()

    def update(self, point: PricePoint) -> None:
        with self._lock:
            self._data[point.ticker] = point

    def get(self, ticker: str) -> PricePoint | None:
        with self._lock:
            return self._data.get(ticker)

    def get_all(self) -> dict[str, PricePoint]:
        with self._lock:
            return dict(self._data)

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._data.pop(ticker, None)
```

---

## Factory Function

```python
# backend/market/factory.py

import os
from .base import MarketDataProvider
from .simulator import SimulatorProvider
from .massive import MassiveProvider


def create_provider(initial_tickers: list[str]) -> MarketDataProvider:
    """Return the appropriate provider based on environment configuration."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveProvider(api_key=api_key, tickers=initial_tickers)
    return SimulatorProvider(tickers=initial_tickers)
```

Called once at application startup, stored as an app-level singleton.

---

## Massive Provider

Polls the Massive API snapshot endpoint on a configurable interval.

```python
# backend/market/massive.py

import asyncio
import httpx
from datetime import datetime, timezone
from .base import MarketDataProvider
from .cache import PriceCache
from .types import PricePoint

BASE_URL = "https://api.massive.com"
POLL_INTERVAL = 15.0  # seconds (safe for free tier: 4 req/min)


class MassiveProvider(MarketDataProvider):
    """Polls Massive REST API for real-time price snapshots."""

    def __init__(self, api_key: str, tickers: list[str]) -> None:
        self._api_key = api_key
        self._tickers: set[str] = set(tickers)
        self._cache = PriceCache()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def add_ticker(self, ticker: str) -> None:
        self._tickers.add(ticker.upper())

    def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker.upper())
        self._cache.remove(ticker.upper())

    def get_price(self, ticker: str) -> PricePoint | None:
        return self._cache.get(ticker.upper())

    def get_all_prices(self) -> dict[str, PricePoint]:
        return self._cache.get_all()

    async def _poll_loop(self) -> None:
        async with httpx.AsyncClient() as client:
            while True:
                if self._tickers:
                    await self._fetch_and_update(client)
                await asyncio.sleep(POLL_INTERVAL)

    async def _fetch_and_update(self, client: httpx.AsyncClient) -> None:
        tickers = list(self._tickers)
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ",".join(tickers), "apiKey": self._api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return  # silently skip failed polls; cache retains last known prices

        for item in data.get("tickers", []):
            ticker = item["ticker"]
            if "lastTrade" not in item:
                continue
            new_price = item["lastTrade"]["p"]
            existing = self._cache.get(ticker)
            prev_price = existing.price if existing else new_price
            direction = "up" if new_price > prev_price else ("down" if new_price < prev_price else "flat")
            self._cache.update(PricePoint(
                ticker=ticker,
                price=new_price,
                previous_price=prev_price,
                timestamp=datetime.now(timezone.utc),
                direction=direction,
            ))

    async def validate_ticker(self, ticker: str) -> bool:
        """Returns True if the ticker exists in the Massive API."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}",
                    params={"apiKey": self._api_key},
                    timeout=10,
                )
                if resp.status_code == 404:
                    return False
                data = resp.json()
                return data.get("status") == "OK" and "ticker" in data
            except Exception:
                return False
```

---

## Simulator Provider

See `MARKET_SIMULATOR.md` for the full design. Summary of interface contract:

```python
# backend/market/simulator.py

class SimulatorProvider(MarketDataProvider):
    """GBM price simulator. Accepts any ticker string. No external calls."""

    def __init__(self, tickers: list[str]) -> None: ...
    async def start(self) -> None: ...   # launches asyncio background task at 500ms
    async def stop(self) -> None: ...
    def add_ticker(self, ticker: str) -> None: ...   # any string accepted
    def remove_ticker(self, ticker: str) -> None: ...
    def get_price(self, ticker: str) -> PricePoint | None: ...
    def get_all_prices(self) -> dict[str, PricePoint]: ...
```

---

## Integration with FastAPI

```python
# backend/main.py (lifespan)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .market.factory import create_provider
from .db import get_watchlist_tickers

provider: MarketDataProvider | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global provider
    tickers = get_watchlist_tickers()  # read from DB
    provider = create_provider(tickers)
    await provider.start()
    yield
    await provider.stop()


app = FastAPI(lifespan=lifespan)
```

The provider is accessed from route handlers via a dependency or module-level reference. The SSE handler loops over `provider.get_all_prices()` to push updates.

---

## SSE Streaming

The SSE endpoint reads from the provider every 500ms and pushes any changed prices:

```python
# backend/routes/stream.py

import asyncio
import json
from fastapi import Request
from fastapi.responses import StreamingResponse
from ..main import provider


async def price_stream(request: Request):
    async def generate():
        last_sent: dict[str, float] = {}
        while not await request.is_disconnected():
            prices = provider.get_all_prices()
            for ticker, point in prices.items():
                if last_sent.get(ticker) != point.price:
                    last_sent[ticker] = point.price
                    payload = {
                        "ticker": point.ticker,
                        "price": point.price,
                        "previous_price": point.previous_price,
                        "timestamp": point.timestamp.isoformat(),
                        "direction": point.direction,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## Watchlist Changes

When a user adds or removes a ticker via the API, the route handler calls the provider directly:

```python
# On add:
provider.add_ticker(ticker)

# On remove:
provider.remove_ticker(ticker)
```

In Massive mode, `add_ticker` for an unknown ticker won't cause an error until the next poll — the route handler should call `validate_ticker` before inserting into the database.
