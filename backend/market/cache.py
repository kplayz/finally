"""Thread-safe in-memory price cache shared by all market data providers."""

import threading

from .types import PricePoint


class PriceCache:
    """Thread-safe in-memory store of the latest PricePoint for each ticker.

    Both SimulatorProvider and MassiveProvider write here; SSE stream
    handlers and API route handlers read from here.  All access is
    protected by a single re-entrant lock so the cache is safe to use
    from asyncio tasks and background threads simultaneously.
    """

    def __init__(self) -> None:
        self._data: dict[str, PricePoint] = {}
        self._lock = threading.Lock()

    def update(self, point: PricePoint) -> None:
        """Insert or replace the PricePoint for ``point.ticker``."""
        with self._lock:
            self._data[point.ticker] = point

    def get(self, ticker: str) -> PricePoint | None:
        """Return the latest PricePoint for *ticker*, or ``None``."""
        with self._lock:
            return self._data.get(ticker)

    def get_all(self) -> dict[str, PricePoint]:
        """Return a shallow copy of the entire cache."""
        with self._lock:
            return dict(self._data)

    def remove(self, ticker: str) -> None:
        """Evict *ticker* from the cache (no-op if not present)."""
        with self._lock:
            self._data.pop(ticker, None)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
