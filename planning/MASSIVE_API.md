# Massive API Reference (formerly Polygon.io)

Polygon.io rebranded as **Massive** on October 30, 2025. The APIs, keys, and services are identical — only the branding changed.

- New base URL: `https://api.massive.com`
- Old base URL: `https://api.polygon.io` (still works, redirected)
- Docs: `https://massive.com/docs`
- Dashboard / API keys: `https://massive.com/dashboard/api-keys`

---

## Authentication

Two methods are supported. Query parameter is most common.

**Query parameter:**
```
GET https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers?apiKey=YOUR_KEY
```

**Authorization header:**
```
Authorization: Bearer YOUR_KEY
```

The official Python client reads from the `POLYGON_API_KEY` environment variable (kept for backward compatibility).

---

## Key Endpoints

All paths relative to `https://api.massive.com`.

### Multi-Ticker Snapshot (primary polling endpoint)

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
  ?tickers=AAPL,MSFT,GOOGL
  &apiKey=YOUR_KEY
```

Returns current state for each ticker in one call. This is the **primary endpoint** for FinAlly's market data poller — fetch all watched tickers with a single HTTP request.

Response:
```json
{
  "count": 2,
  "status": "OK",
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 0.98,
      "todaysChangePerc": 0.82,
      "updated": 1605195918306274000,
      "day": { "o": 119.62, "h": 120.53, "l": 118.81, "c": 120.42, "v": 28727868, "vw": 119.725 },
      "lastTrade": { "p": 120.47, "s": 236, "t": 1605195918306274000, "x": 10 },
      "lastQuote": { "P": 120.47, "S": 4, "p": 120.46, "s": 8, "t": 1605195918507251700 },
      "prevDay": { "o": 117.19, "h": 119.63, "l": 116.44, "c": 119.49, "v": 110597265, "vw": 118.4998 }
    }
  ]
}
```

Key fields:
- `lastTrade.p` — current price
- `prevDay.c` — previous close (for daily change %)
- `todaysChangePerc` — daily change percentage
- `updated` — nanosecond Unix timestamp

### Single Ticker Snapshot

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}?apiKey=YOUR_KEY
```

Same response shape as above but for one ticker, nested under `"ticker"` (singular key).

### Last Trade (single ticker)

```
GET /v2/last/trade/{ticker}?apiKey=YOUR_KEY
```

Response:
```json
{
  "status": "OK",
  "results": {
    "T": "AAPL",
    "p": 129.85,
    "s": 25,
    "t": 1617901342969834000
  }
}
```

`results.p` is the price. `t` is a nanosecond Unix timestamp.

### Previous Day Bar (EOD OHLCV)

```
GET /v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey=YOUR_KEY
```

Response:
```json
{
  "ticker": "AAPL",
  "status": "OK",
  "adjusted": true,
  "results": [
    { "T": "AAPL", "o": 115.55, "h": 117.59, "l": 114.13, "c": 115.97,
      "v": 131704427, "vw": 116.31, "t": 1605042000000 }
  ]
}
```

`t` is millisecond Unix timestamp of the bar start.

### Historical Daily Bars (date range)

```
GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}
  ?adjusted=true&sort=asc&limit=500
  &apiKey=YOUR_KEY
```

- `from`, `to`: `YYYY-MM-DD`
- `timespan`: `second`, `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`
- `limit`: max 50,000, default 5,000

Response — same `results[]` format as prev-day endpoint, multiple entries.

### Unified Snapshot (v3, up to 250 tickers)

```
GET /v3/snapshot?ticker.any_of=AAPL,MSFT,TSLA&apiKey=YOUR_KEY
```

Newer endpoint supporting multiple asset classes. Supports pagination via `next_url`.

---

## Rate Limits

| Tier              | Price        | Requests/min | Real-time? |
|-------------------|--------------|--------------|------------|
| Free (Basic)      | $0           | 5            | No (EOD only) |
| Stocks Developer  | $7/month     | Unlimited    | Yes        |
| Stocks Starter    | $29/month    | Unlimited    | Yes        |
| Stocks Advanced   | $200/month   | Unlimited    | Yes        |

**Free tier strategy**: One multi-ticker snapshot call every 15 seconds = 4 req/min, safe under the 5 req/min cap.

---

## WebSocket Streaming

Massive provides WebSocket streaming (in addition to REST polling). This is available on paid tiers.

- Real-time: `wss://socket.massive.com/stocks`
- Delayed (15 min): `wss://delayed.massive.com/stocks`

Authentication — send immediately after connecting:
```json
{"action": "auth", "params": "YOUR_API_KEY"}
```

Subscribe to trades:
```json
{"action": "subscribe", "params": "T.AAPL"}
```

Channels:
- `T.{ticker}` — tick-level trades
- `Q.{ticker}` — NBBO quotes
- `A.{ticker}` — per-second aggregate bars
- `AM.{ticker}` — per-minute aggregate bars

Trade event payload:
```json
{"ev": "T", "sym": "AAPL", "p": 129.85, "s": 100, "t": 1536036818784}
```

**Note**: FinAlly uses REST polling (not WebSocket) — the SSE architecture handles push to the browser, and REST polling feeds the backend cache. This is simpler and works on all tiers.

---

## Python Code Examples

Install:
```bash
uv add polygon-api-client
```

The package `polygon-api-client` still works (and so does `massive` if the new package is published). Both read `POLYGON_API_KEY` from the environment.

### Direct HTTP with `httpx` (recommended for FinAlly)

```python
import httpx
import os

BASE = "https://api.massive.com"
API_KEY = os.environ["MASSIVE_API_KEY"]


def get_snapshots(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for multiple tickers in one call.

    Returns a dict mapping ticker -> current price.
    """
    resp = httpx.get(
        f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"tickers": ",".join(tickers), "apiKey": API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        item["ticker"]: item["lastTrade"]["p"]
        for item in data.get("tickers", [])
        if "lastTrade" in item
    }


def get_prev_close(tickers: list[str]) -> dict[str, float]:
    """Fetch previous day's close price for multiple tickers."""
    resp = httpx.get(
        f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"tickers": ",".join(tickers), "apiKey": API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        item["ticker"]: item["prevDay"]["c"]
        for item in data.get("tickers", [])
        if "prevDay" in item
    }


def get_daily_bars(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """Fetch daily OHLCV bars for a ticker over a date range."""
    resp = httpx.get(
        f"{BASE}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}",
        params={"adjusted": "true", "sort": "asc", "limit": 500, "apiKey": API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])
```

### Using the Official Client Library

```python
from polygon import RESTClient

client = RESTClient(api_key=os.environ["MASSIVE_API_KEY"])

# Fetch snapshots for multiple tickers
snapshots = client.get_snapshot_all("stocks", tickers=["AAPL", "MSFT", "TSLA"])
for snap in snapshots:
    print(snap.ticker, snap.last_trade.price)
```

---

## Invalid Ticker Handling

If a ticker is not recognized (e.g., a typo like `AAPLL`), the snapshot endpoint silently omits that ticker from the `tickers` array rather than returning an error. The backend should check whether the expected tickers appear in the response and raise an error for any that are missing.

```python
def validate_ticker(ticker: str) -> bool:
    """Returns True if the ticker exists on Massive."""
    resp = httpx.get(
        f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
        params={"apiKey": API_KEY},
        timeout=10,
    )
    if resp.status_code == 404:
        return False
    data = resp.json()
    return data.get("status") == "OK" and "ticker" in data
```
