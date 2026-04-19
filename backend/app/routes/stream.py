"""SSE stream for live price updates. GET /api/stream/prices."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


async def _price_event_stream(request: Request):
    provider = getattr(request.app.state, "market", None)
    cadence_s = getattr(request.app.state, "sse_cadence_s", 0.5)
    # Track last-pushed price per ticker for dedup.
    last_pushed: dict[str, float] = {}

    # Initial snapshot so clients don't stare at an empty UI until first change.
    if provider is not None:
        for ticker, pt in provider.get_all_prices().items():
            last_pushed[ticker] = pt.price
            payload = {
                "ticker": ticker,
                "price": pt.price,
                "previous_price": pt.previous_price,
                "timestamp": pt.timestamp.isoformat()
                if hasattr(pt.timestamp, "isoformat")
                else str(pt.timestamp),
                "direction": pt.direction,
            }
            yield f"data: {json.dumps(payload)}\n\n"

    while True:
        if await request.is_disconnected():
            break
        if provider is not None:
            for ticker, pt in provider.get_all_prices().items():
                if last_pushed.get(ticker) == pt.price:
                    continue
                last_pushed[ticker] = pt.price
                payload = {
                    "ticker": ticker,
                    "price": pt.price,
                    "previous_price": pt.previous_price,
                    "timestamp": pt.timestamp.isoformat()
                    if hasattr(pt.timestamp, "isoformat")
                    else str(pt.timestamp),
                    "direction": pt.direction,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        await asyncio.sleep(cadence_s)


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _price_event_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
