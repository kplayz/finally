"""Abstract base class that all market data providers must implement."""

from abc import ABC, abstractmethod

from .types import PricePoint


class MarketDataProvider(ABC):
    """Common interface for all market data sources.

    Concrete implementations (SimulatorProvider, MassiveProvider) must
    implement every abstract method.  All downstream code—SSE streaming,
    portfolio valuation, watchlist management—depends only on this
    interface, never on a concrete class.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the background data-collection task."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task gracefully, awaiting its completion."""

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Begin tracking *ticker* (case-insensitive; stored as upper-case)."""

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Stop tracking *ticker* and evict it from the price cache."""

    @abstractmethod
    def get_price(self, ticker: str) -> PricePoint | None:
        """Return the latest PricePoint for *ticker*, or ``None`` if not tracked."""

    @abstractmethod
    def get_all_prices(self) -> dict[str, PricePoint]:
        """Return the latest PricePoint for every currently-tracked ticker."""
