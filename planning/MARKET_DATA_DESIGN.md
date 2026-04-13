# Market Data Backend Design
 
## Overview
 
The market data layer provides a unified interface for retrieving stock prices in real time. Two pluggable implementations exist:
 
- **`SimulatorProvider`** — Generates synthetic prices using geometric Brownian motion (GBM), no external dependencies
- **`MassiveProvider`** — Polls the Massive REST API (formerly Polygon.io) for real market data
 
Selection is automatic: if `MASSIVE_API_KEY` environment variable is set and non-empty, the Massive provider is used; otherwise the simulator runs.
 
All downstream code (SSE streaming, API routes, portfolio valuation) reads from a shared thread-safe cache and is completely agnostic to which provider is active.
 
---
 
## Architecture
 
```
┌─────────────────────────────────────────────┐
│       MarketDataProvider (ABC)              │
│  + start() / stop()                         │
│  + add_ticker() / remove_ticker()           │
│  + get_price() / get_all_prices()           │
└────────────┬────────────────────────────────┘
             │ implements
    ┌────────┴─────────┐
    │                  │
SimulatorProvider  MassiveProvider
(GBM simulation     (REST polling
 at 500ms)         every 15s)
    │                  │
    └────────┬─────────┘
             │ writes to
         PriceCache
    (thread-safe dict)
             │ read by
         SSE stream
         API routes
```
 
---
 
## Module Structure
 
```
backend/
└── market/
    ├── __init__.py          # public exports
    ├── types.py             # PricePoint dataclass
    ├── base.py              # MarketDataProvider ABC
    ├── cache.py             # PriceCache (thread-safe)
    ├── simulator.py         # SimulatorProvider
    ├── massive.py           # MassiveProvider
    └── factory.py           # create_provider() factory
```
 
---
 
## 1. Types (`backend/market/types.py`)
 
```python
from dataclasses import dataclass
from datetime import datetime
 
 
@dataclass
class PricePoint:
    """Immutable snapshot of a single ticker's price at a moment in time."""
    ticker: str
    price: float
    previous_price: float
    timestamp: datetime  # always UTC-aware
    direction: str       # "up" | "down" | "flat"
```
 
The `direction` field is computed by the provider when the price is updated (not lazily on read), avoiding repeated comparisons in the SSE loop.
 
---
 
## 2. Abstract Interface (`backend/market/base.py`)
 
```python
from abc import ABC, abstractmethod
from .types import PricePoint
 
 
class MarketDataProvider(ABC):
    """Interface that both simulator and Massive API must implement."""
 
    @abstractmethod
    async def start(self) -> None:
        """
        Launch the background data collection task.
        
        For SimulatorProvider: starts the GBM tick loop.
        For MassiveProvider: starts the REST polling loop.
        """
 
    @abstractmethod
    async def stop(self) -> None:
        """
        Cancel the background task and release resources.
        Safe to call even if start() was never called.
        """
 
    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """
        Begin tracking a new ticker.
        
        For SimulatorProvider: any string is accepted; unknown tickers
        seed at $100.00 with default volatility.
        For MassiveProvider: picks up on next poll; validate beforehand.
        
        Idempotent — calling twice for the same ticker is safe.
        """
 
    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """
        Stop tracking a ticker and evict from the cache.
        No-op if the ticker was not being tracked.
        """
 
    @abstractmethod
    def get_price(self, ticker: str) -> PricePoint | None:
        """
        Return the latest PricePoint for a single ticker.
        Returns None if the ticker is not being tracked.
        """
 
    @abstractmethod
    def get_all_prices(self) -> dict[str, PricePoint]:
        """
        Return a snapshot of all currently tracked tickers.
        Returns a shallow copy — safe to iterate outside the lock.
        """
```
 
---
 
## 3. Price Cache (`backend/market/cache.py`)
 
```python
import threading
from .types import PricePoint
 
 
class PriceCache:
    """
    Thread-safe in-memory store for the latest PricePoint of each ticker.
    
    Shared by all providers (one instance per app). All readers and writers
    use the lock to ensure consistency.
    """
 
    def __init__(self) -> None:
        self._data: dict[str, PricePoint] = {}
        self._lock = threading.Lock()
 
    def update(self, point: PricePoint) -> None:
        """Write a new PricePoint for a ticker, overwriting any previous value."""
        with self._lock:
            self._data[point.ticker] = point
 
    def get(self, ticker: str) -> PricePoint | None:
        """Read the latest PricePoint for a single ticker, or None if missing."""
        with self._lock:
            return self._data.get(ticker)
 
    def get_all(self) -> dict[str, PricePoint]:
        """
        Read all current PricePoints as a new dict.
        
        Returns a shallow copy so the caller can iterate safely
        without holding the lock.
        """
        with self._lock:
            return dict(self._data)
 
    def remove(self, ticker: str) -> None:
        """Evict a ticker from the cache. No-op if not present."""
        with self._lock:
            self._data.pop(ticker, None)
```
 
**Why `threading.Lock` and not `asyncio.Lock`:**
The simulator's `_tick()` method runs synchronously inside an asyncio task (CPU-bound work, no await points inside the loop). `threading.Lock` is correct for mixed sync/async contexts. `asyncio.Lock` would not provide mutual exclusion against the synchronous tick thread.
 
---
 
## 4. Simulator Provider (`backend/market/simulator.py`)
 
### Constants
 
```python
import asyncio
import math
import random
import threading
from datetime import datetime, timezone
 
from .base import MarketDataProvider
from .cache import PriceCache
from .types import PricePoint
 
# Time stepping
TICK_INTERVAL = 0.5  # seconds between price updates
DT = TICK_INTERVAL / 31_536_000  # fraction of a year per tick (≈ 1.59e-8)
 
# Market structure
MARKET_CORRELATION = 0.4  # weight of the common factor in price moves
CORR_COMPLEMENT = math.sqrt(1 - MARKET_CORRELATION ** 2)  # ≈ 0.9165
 
# Random events (earnings surprises, news flashes)
EVENT_PROBABILITY = 0.0005  # per ticker per tick (~once per 30 min)
EVENT_MAGNITUDE = 0.03  # base jump magnitude (±3%)
PRICE_FLOOR = 0.01
 
# Default prices for the 10 seed tickers (as of early 2026)
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
 
DEFAULT_PRICE = 100.0  # seed price for tickers added at runtime
DEFAULT_DRIFT = 0.08  # 8% annualized return
DEFAULT_VOL = 0.30  # 30% annualized volatility
 
# Per-ticker vol overrides for realistic feel
TICKER_VOL: dict[str, float] = {
    "TSLA": 0.55,  # high vol (growth)
    "NVDA": 0.50,  # high vol (semiconductor)
    "AAPL": 0.22,  # lower vol (large cap)
    "JPM":  0.20,  # lower vol (bank)
    "V":    0.18,  # lower vol (payments)
}
```
 
### Implementation
 
```python
class SimulatorProvider(MarketDataProvider):
    """
    Generates synthetic stock prices using geometric Brownian motion.
    
    No external API calls. Accepts any ticker string. Provides realistic
    price movements via GBM with market correlation and random events.
    """
 
    def __init__(self, tickers: list[str]) -> None:
        self._cache = PriceCache()
        self._lock = threading.Lock()
        self._prices: dict[str, float] = {}  # in-memory price state
        self._task: asyncio.Task | None = None
 
        # Initialize seed prices for all starting tickers
        for ticker in tickers:
            self._init_ticker(ticker.upper())
 
    # ================================================================ lifecycle
 
    async def start(self) -> None:
        """Launch the background tick loop."""
        self._task = asyncio.create_task(self._tick_loop())
 
    async def stop(self) -> None:
        """Cancel the tick loop and wait for cleanup."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
 
    # ================================================================ mutations
 
    def add_ticker(self, ticker: str) -> None:
        """Begin tracking a new ticker. Idempotent."""
        ticker = ticker.upper()
        with self._lock:
            if ticker not in self._prices:
                self._init_ticker(ticker)
 
    def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker and evict from cache."""
        ticker = ticker.upper()
        with self._lock:
            self._prices.pop(ticker, None)
        self._cache.remove(ticker)
 
    # ================================================================ reads
 
    def get_price(self, ticker: str) -> PricePoint | None:
        """Fetch latest PricePoint for a ticker."""
        return self._cache.get(ticker.upper())
 
    def get_all_prices(self) -> dict[str, PricePoint]:
        """Fetch all current PricePoints."""
        return self._cache.get_all()
 
    # ================================================================ internals
 
    def _init_ticker(self, ticker: str) -> None:
        """
        Initialize a ticker with its seed price and write initial PricePoint.
        
        Caller must hold self._lock (called from __init__ or add_ticker).
        """
        price = SEED_PRICES.get(ticker, DEFAULT_PRICE)
        self._prices[ticker] = price
        self._cache.update(PricePoint(
            ticker=ticker,
            price=price,
            previous_price=price,
            timestamp=datetime.now(timezone.utc),
            direction="flat",
        ))
 
    async def _tick_loop(self) -> None:
        """
        Main background loop: sleep, call _tick().
        Runs continuously until cancelled.
        """
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            self._tick()
 
    def _tick(self) -> None:
        """
        Execute one tick: advance all tracked tickers' prices via GBM.
        
        This is the core simulation engine. Called every 500ms.
        """
        # Generate one market-wide shock for all tickers this tick
        market_shock = random.gauss(0, 1)
        now = datetime.now(timezone.utc)
 
        # Snapshot the current ticker list (holding lock briefly)
        with self._lock:
            tickers = list(self._prices.keys())
 
        # Process each ticker
        for ticker in tickers:
            # Read current price (holding lock briefly)
            with self._lock:
                if ticker not in self._prices:
                    continue  # ticker was removed mid-iteration, skip it
                old_price = self._prices[ticker]
 
            # Compute parameters for this ticker's GBM step
            vol = TICKER_VOL.get(ticker, DEFAULT_VOL)
            idio = random.gauss(0, 1)  # idiosyncratic (ticker-specific) shock
 
            # Combine market and idiosyncratic shocks via correlation
            Z = MARKET_CORRELATION * market_shock + CORR_COMPLEMENT * idio
 
            # GBM formula: ln(S_t+1 / S_t) = (μ - σ²/2)Δt + σ√Δt Z
            log_return = (DEFAULT_DRIFT - 0.5 * vol ** 2) * DT + vol * math.sqrt(DT) * Z
            new_price = old_price * math.exp(log_return)
 
            # Occasional news/earnings event: sudden jump
            if random.random() < EVENT_PROBABILITY:
                direction = random.choice([1, -1])
                jump_size = direction * EVENT_MAGNITUDE * random.uniform(0.5, 1.5)
                new_price *= 1 + jump_size
 
            # Never let price go negative (financial floor)
            new_price = max(new_price, PRICE_FLOOR)
 
            # Write updated price (holding lock briefly)
            with self._lock:
                self._prices[ticker] = new_price
 
            # Determine direction and update cache
            direction_str = (
                "up" if new_price > old_price
                else ("down" if new_price < old_price else "flat")
            )
            self._cache.update(PricePoint(
                ticker=ticker,
                price=round(new_price, 4),
                previous_price=round(old_price, 4),
                timestamp=now,
                direction=direction_str,
            ))
```
 
**Key design notes:**
- The lock is held very briefly (just for price reads/writes), not across the entire GBM computation. This allows `add_ticker` / `remove_ticker` to be responsive even during a tick.
- The `continue` guard handles the race where a ticker is removed via `remove_ticker()` while the loop is iterating.
- `datetime.now(timezone.utc)` is called once per tick, so all prices in that tick share the same timestamp.
- Rounding to 4 decimal places ($0.0001) is typical for stock prices but avoids floating-point precision issues.
 
---
 
## 5. Massive Provider (`backend/market/massive.py`)
 
### Configuration
 
```python
import asyncio
import httpx
from datetime import datetime, timezone
 
from .base import MarketDataProvider
from .cache import PriceCache
from .types import PricePoint
 
BASE_URL = "https://api.massive.com"
POLL_INTERVAL = 15.0  # seconds
# Safe under free-tier limit of 5 req/min: 60 / 15 = 4 req/min
```
 
### Implementation
 
```python
class MassiveProvider(MarketDataProvider):
    """
    Polls the Massive REST API for real-time stock prices.
    
    Uses the `/v2/snapshot` endpoint to fetch current prices for all
    watched tickers in a single HTTP request. Tolerates transient failures
    gracefully — stale cache is preferable to a crashed stream.
    """
 
    def __init__(self, api_key: str, tickers: list[str]) -> None:
        self._api_key = api_key
        self._tickers: set[str] = {t.upper() for t in tickers}
        self._cache = PriceCache()
        self._task: asyncio.Task | None = None
 
    # ================================================================ lifecycle
 
    async def start(self) -> None:
        """Launch the background REST polling loop."""
        self._task = asyncio.create_task(self._poll_loop())
 
    async def stop(self) -> None:
        """Cancel the polling loop and release resources."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
 
    # ================================================================ mutations
 
    def add_ticker(self, ticker: str) -> None:
        """
        Begin tracking a ticker. Picked up on the next poll.
        
        In production, callers should call validate_ticker() first
        to avoid tracking bogus symbols.
        """
        self._tickers.add(ticker.upper())
 
    def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker and evict from cache."""
        self._tickers.discard(ticker.upper())
        self._cache.remove(ticker.upper())
 
    # ================================================================ reads
 
    def get_price(self, ticker: str) -> PricePoint | None:
        """Fetch latest PricePoint for a ticker."""
        return self._cache.get(ticker.upper())
 
    def get_all_prices(self) -> dict[str, PricePoint]:
        """Fetch all current PricePoints."""
        return self._cache.get_all()
 
    # ================================================================ internals
 
    async def _poll_loop(self) -> None:
        """
        Main background loop: every POLL_INTERVAL seconds, fetch snapshots.
        
        Runs continuously until cancelled. Opens a single long-lived
        httpx.AsyncClient for connection pooling.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                if self._tickers:
                    await self._fetch_and_update(client)
                await asyncio.sleep(POLL_INTERVAL)
 
    async def _fetch_and_update(self, client: httpx.AsyncClient) -> None:
        """
        Fetch snapshots from Massive and update the cache.
        
        Silently tolerates network errors — cache retains last known prices.
        """
        tickers = list(self._tickers)
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ",".join(tickers), "apiKey": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            # Network error, timeout, or invalid JSON — skip this poll
            return
 
        # Parse the response and update cache for each ticker
        for item in data.get("tickers", []):
            ticker = item.get("ticker")
            if not ticker or "lastTrade" not in item:
                continue
 
            new_price = item["lastTrade"]["p"]
            existing = self._cache.get(ticker)
 
            # Compute previous price and direction
            prev_price = existing.price if existing else new_price
            direction = (
                "up" if new_price > prev_price
                else ("down" if new_price < prev_price else "flat")
            )
 
            self._cache.update(PricePoint(
                ticker=ticker,
                price=new_price,
                previous_price=prev_price,
                timestamp=datetime.now(timezone.utc),
                direction=direction,
            ))
 
    async def validate_ticker(self, ticker: str) -> bool:
        """
        Check if a ticker exists in the Massive API.
        
        Called by the watchlist ADD route before inserting into the DB.
        Returns False if the ticker is unknown.
        
        Uses a separate short-lived client because this is an ad-hoc call,
        not part of the polling loop.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}",
                    params={"apiKey": self._api_key},
                )
                if resp.status_code == 404:
                    return False
                data = resp.json()
                return data.get("status") == "OK" and "ticker" in data
            except Exception:
                # Network error, timeout, etc. — treat as unvalidated.
                # Caller decides whether to reject.
                return False
```
 
**Key design notes:**
- The single `httpx.AsyncClient` opened in `_poll_loop` uses connection pooling, making each poll cheap.
- `validate_ticker` opens its own short-lived client because it's called ad-hoc from routes, not in the tight polling loop.
- Failed polls are silently skipped. A transient network glitch should not interrupt SSE or block the app.
- When Massive silently omits an invalid ticker from the snapshot response, we never write it to the cache, so `validate_ticker` catches it.
 
---
 
## 6. Factory (`backend/market/factory.py`)
 
```python
import os
from .base import MarketDataProvider
from .simulator import SimulatorProvider
from .massive import MassiveProvider
 
 
def create_provider(initial_tickers: list[str]) -> MarketDataProvider:
    """
    Select and instantiate the appropriate provider.
    
    If MASSIVE_API_KEY environment variable is set and non-empty,
    returns MassiveProvider. Otherwise returns SimulatorProvider.
    
    Called once at application startup.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveProvider(api_key=api_key, tickers=initial_tickers)
    return SimulatorProvider(tickers=initial_tickers)
```
 
---
 
## 7. Package Init (`backend/market/__init__.py`)
 
```python
from .factory import create_provider
from .base import MarketDataProvider
from .types import PricePoint
 
__all__ = [
    "create_provider",
    "MarketDataProvider",
    "PricePoint",
]
```
 
Only these three symbols are exported. Internal modules (simulator, massive, cache, factory) are accessed only within the package.
 
---
 
## 8. FastAPI Integration
 
### App Startup/Shutdown (`backend/main.py`)
 
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .market import create_provider, MarketDataProvider
from .db import get_watchlist_tickers
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager: initialize the provider on startup,
    tear down on shutdown.
    """
    # Read the initial watchlist from the DB
    tickers = get_watchlist_tickers()  # returns list[str]
 
    # Create the provider (simulator or Massive, based on env var)
    provider = create_provider(tickers)
 
    # Store on app state for access in route handlers
    app.state.provider = provider
 
    # Launch the background task
    await provider.start()
 
    yield
 
    # Cleanup on shutdown
    await provider.stop()
 
 
# Create the app with the lifespan context
app = FastAPI(lifespan=lifespan)
```
 
### Dependency Injection (`backend/deps.py`)
 
```python
from fastapi import Request
from .market import MarketDataProvider
 
 
def get_provider(request: Request) -> MarketDataProvider:
    """Dependency that returns the app-level provider instance."""
    return request.app.state.provider
```
 
Routes then inject the provider:
```python
from fastapi import Depends
from .deps import get_provider
 
@app.get("/api/prices")
async def get_prices(provider: MarketDataProvider = Depends(get_provider)):
    return provider.get_all_prices()
```
 
---
 
## 9. SSE Streaming Endpoint (`backend/routes/stream.py`)
 
```python
import asyncio
import json
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from ..deps import get_provider
from ..market import MarketDataProvider
 
router = APIRouter()
 
 
@router.get("/api/stream/prices")
async def price_stream(
    request: Request,
    provider: MarketDataProvider = Depends(get_provider),
):
    """
    Server-Sent Events endpoint for real-time price updates.
    
    Clients connect via:
        const es = new EventSource('/api/stream/prices');
        es.addEventListener('message', (evt) => {
            const data = JSON.parse(evt.data);
            console.log(data);  // {ticker, price, previous_price, timestamp, direction}
        });
    
    The stream only sends an event when a price has changed since the last
    push (avoiding duplicate events for unchanged tickers, especially important
    for the Massive provider which polls every 15s).
    """
 
    async def generate():
        # Per-connection state: last price sent for each ticker
        last_sent: dict[str, float] = {}
 
        while not await request.is_disconnected():
            # Fetch all current prices (thread-safe snapshot)
            prices = provider.get_all_prices()
 
            # Emit only changed prices
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
 
            # Yield control and wait before next batch
            await asyncio.sleep(0.5)
 
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering if proxied
        },
    )
```
 
**Key design notes:**
- The `last_sent` dict is per-connection local state — no shared mutable structures needed.
- `request.is_disconnected()` detects client disconnection (browser tab closed, network drop).
- The generator exits cleanly on disconnect, and `StreamingResponse` closes the connection.
- 500ms sleep matches the simulator's tick interval — sync'd timing for responsiveness.
 
---
 
## 10. Watchlist Routes (`backend/routes/watchlist.py`)
 
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..deps import get_provider
from ..market import MarketDataProvider
from ..market.massive import MassiveProvider
from ..db import add_watchlist_ticker, remove_watchlist_ticker
 
router = APIRouter()
 
 
class AddTickerRequest(BaseModel):
    ticker: str
 
 
@router.post("/api/watchlist")
async def add_ticker(
    body: AddTickerRequest,
    provider: MarketDataProvider = Depends(get_provider),
):
    """
    Add a ticker to the user's watchlist.
    
    If in Massive mode: validates the ticker exists before persisting.
    If in simulator mode: accepts any string (useful for demos).
    """
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
 
    # In Massive mode: validate before DB insert
    if isinstance(provider, MassiveProvider):
        valid = await provider.validate_ticker(ticker)
        if not valid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown ticker: {ticker}",
            )
 
    # Insert into DB (UNIQUE constraint on (user_id, ticker) handles duplicates)
    add_watchlist_ticker(ticker)
 
    # Start tracking prices
    provider.add_ticker(ticker)
 
    return {"ticker": ticker, "status": "added"}
 
 
@router.delete("/api/watchlist/{ticker}")
async def remove_ticker(
    ticker: str,
    provider: MarketDataProvider = Depends(get_provider),
):
    """Remove a ticker from the user's watchlist."""
    ticker = ticker.upper()
 
    # Remove from DB
    remove_watchlist_ticker(ticker)
 
    # Stop tracking prices and evict from cache
    provider.remove_ticker(ticker)
 
    return {"ticker": ticker, "status": "removed"}
```
 
**Why `isinstance(provider, MassiveProvider)`:**
This is the only place in route code that knows about a concrete provider type. It's isolated here because validation is semantically different:
- Simulator: accepts any string (no external validation needed)
- Massive: must validate against real-world symbols
 
---
 
## 11. Portfolio Routes: Market Data Integration
 
Routes that fetch portfolio data call `provider.get_all_prices()` to compute unrealized P&L:
 
```python
from ..deps import get_provider
from ..market import MarketDataProvider
from ..db import get_positions
 
@router.get("/api/portfolio")
async def get_portfolio(
    provider: MarketDataProvider = Depends(get_provider),
):
    """
    Return current portfolio state with live prices.
    """
    positions = get_positions()  # from DB: (ticker, quantity, avg_cost)
    all_prices = provider.get_all_prices()
 
    result_positions = []
    for pos in positions:
        ticker = pos["ticker"]
        point = all_prices.get(ticker)
        if not point:
            continue  # not being tracked, skip
        
        current_price = point.price
        unrealized_pnl = (current_price - pos["avg_cost"]) * pos["quantity"]
        pnl_percent = ((current_price / pos["avg_cost"]) - 1) * 100
 
        result_positions.append({
            "ticker": ticker,
            "quantity": pos["quantity"],
            "avg_cost": pos["avg_cost"],
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "pnl_percent": pnl_percent,
        })
 
    total_value = sum(p["current_price"] * p["quantity"] for p in result_positions)
    cash_balance = get_cash_balance()
    total_value += cash_balance
 
    return {
        "cash_balance": cash_balance,
        "total_value": total_value,
        "positions": result_positions,
    }
```
 
---
 
## 12. Error Handling
 
### Provider-Level
 
| Scenario | Behavior |
|----------|----------|
| Massive poll HTTP 500 | Caught by `except Exception`, poll skipped, cache retains last price |
| Massive poll timeout (>10s) | `httpx.TimeoutException` caught, poll skipped |
| Massive poll invalid JSON | `json.JSONDecodeError` caught, poll skipped |
| Unknown ticker in Massive mode | Silently omitted from snapshot; `get_price()` returns None |
| Ticker removed while simulator ticking | `continue` guard in `_tick()` skips it |
| Client disconnect during SSE | `is_disconnected()` exits generator on next 500ms cycle |
| App shutdown during SSE | Provider `stop()` cancels task; active generators drain naturally |
| Network glitch in `validate_ticker` | Returns `False`; caller (route handler) rejects with HTTP 400 |
 
### Route-Level
 
```python
from fastapi import HTTPException
 
# In add_ticker route:
if isinstance(provider, MassiveProvider):
    valid = await provider.validate_ticker(ticker)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")
```
 
---
 
## 13. Testing Strategy
 
### Unit Tests: Simulator (`backend/tests/test_simulator.py`)
 
```python
import asyncio
import math
from backend.market.simulator import SimulatorProvider
 
 
async def test_simulator_price_stays_positive():
    """Over 10,000 ticks with high volatility, price should never go below PRICE_FLOOR."""
    provider = SimulatorProvider(["TEST"])
    await provider.start()
    
    for _ in range(10_000):
        await asyncio.sleep(0.001)  # don't actually wait 500ms
    
    price_point = provider.get_price("TEST")
    assert price_point.price >= 0.01
    await provider.stop()
 
 
async def test_simulator_market_correlation():
    """Log returns of two tickers should exhibit ~40% correlation."""
    provider = SimulatorProvider(["A", "B"])
    await provider.start()
 
    returns_a, returns_b = [], []
    prev_a, prev_b = 100, 100
 
    for _ in range(1_000):
        await asyncio.sleep(0.001)
        pa = provider.get_price("A")
        pb = provider.get_price("B")
        
        if pa and pb:
            returns_a.append(math.log(pa.price / prev_a))
            returns_b.append(math.log(pb.price / prev_b))
            prev_a, prev_b = pa.price, pb.price
 
    # Compute correlation
    mean_a = sum(returns_a) / len(returns_a)
    mean_b = sum(returns_b) / len(returns_b)
    cov = sum((returns_a[i] - mean_a) * (returns_b[i] - mean_b) for i in range(len(returns_a))) / len(returns_a)
    std_a = (sum((r - mean_a) ** 2 for r in returns_a) / len(returns_a)) ** 0.5
    std_b = (sum((r - mean_b) ** 2 for r in returns_b) / len(returns_b)) ** 0.5
    corr = cov / (std_a * std_b)
 
    # Should be around 0.4 (40% correlation)
    assert 0.2 < corr < 0.6
 
    await provider.stop()
 
 
def test_simulator_unknown_ticker_seeds_at_default():
    """Adding an unknown ticker should seed at $100.00."""
    provider = SimulatorProvider([])
    provider.add_ticker("NOTREAL")
    
    price_point = provider.get_price("NOTREAL")
    assert price_point.price == 100.0
 
 
async def test_simulator_add_remove():
    """Adding and removing tickers should work correctly."""
    provider = SimulatorProvider(["AAPL"])
    await provider.start()
 
    assert provider.get_price("AAPL") is not None
    
    provider.remove_ticker("AAPL")
    assert provider.get_price("AAPL") is None
 
    await provider.stop()
```
 
### Unit Tests: Massive (`backend/tests/test_massive.py`)
 
```python
import pytest
from unittest.mock import AsyncMock, patch
from backend.market.massive import MassiveProvider
 
 
@pytest.mark.asyncio
async def test_massive_updates_cache_on_poll(httpx_mock):
    """Mock snapshot response; assert cache is updated correctly."""
    provider = MassiveProvider(api_key="test_key", tickers=["AAPL"])
 
    mock_response = {
        "status": "OK",
        "tickers": [
            {
                "ticker": "AAPL",
                "lastTrade": {"p": 150.25},
                "prevDay": {"c": 150.00},
            }
        ]
    }
 
    httpx_mock.add_response(json=mock_response)
 
    await provider.start()
    await asyncio.sleep(0.1)  # let poll loop run once
 
    price_point = provider.get_price("AAPL")
    assert price_point.price == 150.25
    assert price_point.direction == "up"
 
    await provider.stop()
 
 
@pytest.mark.asyncio
async def test_massive_failed_poll_retains_cache(httpx_mock):
    """Failed poll (HTTP 500) should not clear the cache."""
    provider = MassiveProvider(api_key="test_key", tickers=["AAPL"])
 
    # First successful poll
    httpx_mock.add_response(json={
        "status": "OK",
        "tickers": [{"ticker": "AAPL", "lastTrade": {"p": 150.00}}]
    })
 
    await provider.start()
    await asyncio.sleep(0.1)
 
    # Verify price was cached
    assert provider.get_price("AAPL").price == 150.00
 
    # Next poll fails
    httpx_mock.add_response(status_code=500)
    await asyncio.sleep(15.1)  # wait for next poll interval
 
    # Cache should still have old price
    assert provider.get_price("AAPL").price == 150.00
 
    await provider.stop()
 
 
@pytest.mark.asyncio
async def test_massive_validate_ticker_unknown(httpx_mock):
    """Unknown ticker should return False."""
    provider = MassiveProvider(api_key="test_key", tickers=[])
 
    httpx_mock.add_response(status_code=404)
 
    valid = await provider.validate_ticker("NOTREAL")
    assert valid is False
 
 
@pytest.mark.asyncio
async def test_massive_validate_ticker_known(httpx_mock):
    """Known ticker should return True."""
    provider = MassiveProvider(api_key="test_key", tickers=[])
 
    httpx_mock.add_response(json={
        "status": "OK",
        "ticker": {"ticker": "AAPL", "lastTrade": {"p": 150.00}}
    })
 
    valid = await provider.validate_ticker("AAPL")
    assert valid is True
```
 
### Cache Tests (`backend/tests/test_cache.py`)
 
```python
import threading
from backend.market.cache import PriceCache
from backend.market.types import PricePoint
from datetime import datetime, timezone
 
 
def test_cache_thread_safety():
    """Concurrent reads and writes should not raise exceptions."""
    cache = PriceCache()
    errors = []
 
    def writer(i):
        try:
            for j in range(100):
                cache.update(PricePoint(
                    ticker=f"T{i}",
                    price=100.0 + j,
                    previous_price=100.0,
                    timestamp=datetime.now(timezone.utc),
                    direction="up",
                ))
        except Exception as e:
            errors.append(e)
 
    def reader():
        try:
            for _ in range(100):
                cache.get_all()
        except Exception as e:
            errors.append(e)
 
    writers = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    readers = [threading.Thread(target=reader) for _ in range(10)]
 
    for t in writers + readers:
        t.start()
 
    for t in writers + readers:
        t.join()
 
    assert len(errors) == 0
```
 
### SSE Tests (`backend/tests/test_stream.py`)
 
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app
from backend.market.types import PricePoint
from datetime import datetime, timezone
 
 
def test_sse_stream_emits_only_changed_prices():
    """SSE should only emit events when a price changes."""
    client = TestClient(app)
 
    # Mock provider
    mock_provider = MagicMock()
    mock_provider.get_all_prices.return_value = {
        "AAPL": PricePoint(
            ticker="AAPL",
            price=150.00,
            previous_price=149.00,
            timestamp=datetime.now(timezone.utc),
            direction="up",
        )
    }
 
    with patch("backend.routes.stream.get_provider", return_value=mock_provider):
        response = client.get("/api/stream/prices", stream=True)
        assert response.status_code == 200
 
        lines = response.iter_lines()
        first_line = next(lines, None)
        assert first_line  # Should have emitted the price
 
        # Call again with same price — should not emit
        mock_provider.get_all_prices.return_value = {
            "AAPL": PricePoint(
                ticker="AAPL",
                price=150.00,  # unchanged
                previous_price=149.00,
                timestamp=datetime.now(timezone.utc),
                direction="flat",
            )
        }
 
        second_line = next(lines, None)
        assert second_line is None  # No new event
```
 
---
 
## 14. Deployment Considerations
 
### Environment Variables
 
```bash
# Required for Massive mode
MASSIVE_API_KEY=your-api-key-here
 
# Optional: mock mode for testing (deterministic responses)
# Set to "true" for E2E tests; omit or set to "false" for production
LLM_MOCK=false
```
 
### Performance Expectations
 
| Component | Update Interval | Latency | Throughput |
|-----------|-----------------|---------|------------|
| SimulatorProvider | 500ms | <1ms cache write | N/A |
| MassiveProvider | 15s | 1-5s API response | 1 request per 15s |
| SSE stream | 500ms | <100ms event push | 10-100 events/sec per ticker |
 
### Production Monitoring
 
Monitor these metrics:
- **SSE connection count**: gauge of active client connections
- **Price cache size**: should grow to watchlist size and plateau
- **Poll latency (Massive mode)**: P50, P95, P99 milliseconds
- **Failed polls (Massive mode)**: count and reason (timeout, HTTP error, etc.)
 
---
 
## 15. Summary
 
The market data backend is a clean abstraction with two concrete implementations:
 
- **SimulatorProvider**: Realistic GBM prices, no external deps, useful for demos and development
- **MassiveProvider**: Real market data, production-ready, handles network failures gracefully
 
Both implement the same interface and write to a shared thread-safe cache. Downstream code (SSE, routes, portfolio) is completely decoupled from the data source — switching between simulator and real market data is a single environment variable.
 
The system is designed to:
- Stream prices efficiently (500ms cadence, change-only emits)
- Handle dynamic ticker management (add/remove at runtime)
- Tolerate transient failures (Massive mode)
- Scale to many concurrent SSE clients (shared cache, no per-client polling)