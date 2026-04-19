"""Deterministic mock LLM for tests and no-key environments.

Responds to a small set of keyword patterns in a predictable way so E2E tests
can exercise the full chat → trade → refresh loop without calling OpenRouter.
"""

from __future__ import annotations

import re

from .schema import LLMOutput


def mock_respond(user_message: str, *, watchlist: list[str]) -> LLMOutput:
    msg = user_message.strip().lower()

    # "buy N SYM" / "sell N SYM"
    m = re.search(r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+([a-z]{1,8})\b", msg)
    if m:
        side = m.group(1)
        qty = float(m.group(2))
        sym = m.group(3).upper()
        return LLMOutput(
            message=f"Done — {side}ing {qty} {sym} at market.",
            trades=[{"ticker": sym, "side": side, "quantity": qty}],
            watchlist_changes=[],
        )

    # "add SYM" / "watch SYM"
    m = re.search(r"\b(?:add|watch)\s+([a-z]{1,8})\b", msg)
    if m:
        sym = m.group(1).upper()
        return LLMOutput(
            message=f"Added {sym} to your watchlist.",
            trades=[],
            watchlist_changes=[{"ticker": sym, "action": "add"}],
        )

    # "remove SYM" / "unwatch SYM" / "drop SYM"
    m = re.search(r"\b(?:remove|unwatch|drop)\s+([a-z]{1,8})\b", msg)
    if m:
        sym = m.group(1).upper()
        return LLMOutput(
            message=f"Removed {sym} from your watchlist.",
            trades=[],
            watchlist_changes=[{"ticker": sym, "action": "remove"}],
        )

    # Portfolio summary
    if any(k in msg for k in ("portfolio", "positions", "how am i", "performance")):
        return LLMOutput(
            message=(
                "Your portfolio snapshot is in the context panel on the left. "
                "Ask me for specific trades or analysis."
            ),
            trades=[],
            watchlist_changes=[],
        )

    return LLMOutput(
        message="(mock) Hi — I can buy/sell, add/remove tickers, or analyze your positions.",
        trades=[],
        watchlist_changes=[],
    )
