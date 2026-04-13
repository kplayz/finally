"""Factory function for selecting the appropriate market data provider.

Selection is driven by the MASSIVE_API_KEY environment variable:
- Set and non-empty  →  MassiveProvider (real market data via REST polling)
- Absent or empty    →  SimulatorProvider (GBM simulation, no external calls)
"""

import os

from .base import MarketDataProvider
from .massive import MassiveProvider
from .simulator import SimulatorProvider


def create_provider(initial_tickers: list[str]) -> MarketDataProvider:
    """Return the appropriate MarketDataProvider for the current environment.

    Called once at application startup; the returned provider is stored
    as an app-level singleton and passed into FastAPI's lifespan context.

    Args:
        initial_tickers: Tickers already in the watchlist (from the DB).
            The provider will begin tracking these immediately on start.

    Returns:
        A :class:`MassiveProvider` if ``MASSIVE_API_KEY`` is set and
        non-empty, otherwise a :class:`SimulatorProvider`.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveProvider(api_key=api_key, tickers=initial_tickers)
    return SimulatorProvider(tickers=initial_tickers)
