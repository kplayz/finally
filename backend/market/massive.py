"""Massive (formerly Polygon.io) REST API market data provider.

Polls the Massive snapshot endpoint on a configurable interval and
writes results to the shared PriceCache.  Used when MASSIVE_API_KEY
is set in the environment.

Docs: https://massive.com/docs
Base URL: https://api.massive.com
"""

import asyncio
from datetime import datetime, timezone

import httpx

from .base import MarketDataProvider
from .cache import PriceCache
from .types import PricePoint

BASE_URL = "https://api.massive.com"

# Free tier: 5 req/min cap — poll every 15 s uses only 4 req/min.
POLL_INTERVAL: float = 15.0  # seconds


class MassiveProvider(MarketDataProvider):
    """Polls the Massive REST API for real-time price snapshots.

    A single background asyncio task fires every POLL_INTERVAL seconds,
    fetches a multi-ticker snapshot in one HTTP request, and writes the
    results to the internal PriceCache.

    Ticker validation via :meth:`validate_ticker` is a separate,
    on-demand HTTP call used by the watchlist add endpoint before the
    ticker is persisted to the database.
    """

    def __init__(self, api_key: str, tickers: list[str]) -> None:
        self._api_key = api_key
        self._tickers: set[str] = {t.upper() for t in tickers}
        self._cache = PriceCache()
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # MarketDataProvider interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the REST polling loop as an asyncio background task."""
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Cancel the polling loop and wait for it to finish."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def add_ticker(self, ticker: str) -> None:
        """Add *ticker* to the poll set (upper-cased)."""
        self._tickers.add(ticker.upper())

    def remove_ticker(self, ticker: str) -> None:
        """Remove *ticker* from the poll set and evict it from the cache."""
        ticker = ticker.upper()
        self._tickers.discard(ticker)
        self._cache.remove(ticker)

    def get_price(self, ticker: str) -> PricePoint | None:
        return self._cache.get(ticker.upper())

    def get_all_prices(self) -> dict[str, PricePoint]:
        return self._cache.get_all()

    # ------------------------------------------------------------------
    # Validation helper (called by watchlist add route)
    # ------------------------------------------------------------------

    async def validate_ticker(self, ticker: str) -> bool:
        """Return ``True`` if *ticker* is recognised by the Massive API.

        Makes a single-ticker snapshot request and checks for a 200 OK
        response with ``status == "OK"`` and a ``"ticker"`` key in the
        JSON body.  Returns ``False`` on 404 or any network/parse error.
        """
        url = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    url,
                    params={"apiKey": self._api_key},
                    timeout=10,
                )
                if resp.status_code == 404:
                    return False
                data = resp.json()
                return data.get("status") == "OK" and "ticker" in data
            except Exception:
                return False

    # ------------------------------------------------------------------
    # Background polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        async with httpx.AsyncClient() as client:
            while True:
                if self._tickers:
                    await self._fetch_and_update(client)
                await asyncio.sleep(POLL_INTERVAL)

    async def _fetch_and_update(self, client: httpx.AsyncClient) -> None:
        """Fetch a multi-ticker snapshot and update the price cache.

        Errors are swallowed so that transient network failures or rate-
        limit responses do not crash the poller; the cache retains the
        last known prices until the next successful poll.
        """
        tickers = list(self._tickers)
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers",
                params={
                    "tickers": ",".join(tickers),
                    "apiKey": self._api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return  # silently skip; cache holds last known prices

        now = datetime.now(timezone.utc)
        for item in data.get("tickers", []):
            ticker = item.get("ticker")
            if not ticker:
                continue
            last_trade = item.get("lastTrade")
            if last_trade is None:
                continue

            new_price: float = last_trade["p"]
            existing = self._cache.get(ticker)
            prev_price = existing.price if existing is not None else new_price
            direction = (
                "up"   if new_price > prev_price else
                "down" if new_price < prev_price else
                "flat"
            )
            self._cache.update(
                PricePoint(
                    ticker=ticker,
                    price=new_price,
                    previous_price=prev_price,
                    timestamp=now,
                    direction=direction,
                )
            )
