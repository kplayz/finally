"""Shared data structures for market data."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PricePoint:
    """A single price observation for a ticker."""

    ticker: str
    price: float
    previous_price: float
    timestamp: datetime
    direction: str  # "up", "down", or "flat"
