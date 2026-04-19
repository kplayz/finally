"""Structured output schema for the chat LLM."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMTrade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class LLMWatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LLMOutput(BaseModel):
    message: str
    trades: list[LLMTrade] = Field(default_factory=list)
    watchlist_changes: list[LLMWatchlistChange] = Field(default_factory=list)
