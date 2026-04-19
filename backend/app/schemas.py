"""Pydantic request/response models. Mirrors planning/PLAN.md §8."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Side = Literal["buy", "sell"]


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    quantity: float = Field(gt=0)
    side: Side

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class TradeResponse(BaseModel):
    ticker: str
    side: Side
    quantity: float
    price: float
    total_cost: float
    cash_remaining: float


class PositionOut(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    unrealized_pnl: float
    pnl_percent: float


class PortfolioOut(BaseModel):
    cash_balance: float
    total_value: float
    positions: list[PositionOut]


class Snapshot(BaseModel):
    total_value: float
    recorded_at: str


class PortfolioHistoryOut(BaseModel):
    snapshots: list[Snapshot]


class WatchlistEntryOut(BaseModel):
    ticker: str
    price: float | None
    previous_price: float | None
    added_at: str


class WatchlistOut(BaseModel):
    watchlist: list[WatchlistEntryOut]


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatTrade(BaseModel):
    ticker: str
    side: Side
    quantity: float
    price: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class ChatResponse(BaseModel):
    message: str
    trades: list[ChatTrade]
    watchlist_changes: list[WatchlistChange]
    errors: list[str]
