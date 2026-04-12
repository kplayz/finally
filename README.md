# FinAlly -- AI Trading Workstation

AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades via natural language.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** -- $10k virtual cash, market orders, fractional shares
- **Portfolio visualizations** -- heatmap, P&L chart, positions table
- **AI chat assistant** -- analyzes holdings, suggests and auto-executes trades
- **Watchlist management** -- track tickers manually or via AI
- **Dark terminal aesthetic** -- Bloomberg-inspired, data-dense layout

## Architecture

Single Docker container on port 8000:

- **Frontend**: Next.js static export, TypeScript, Tailwind CSS
- **Backend**: FastAPI (Python/uv), SSE streaming, SQLite
- **AI**: LiteLLM via OpenRouter (Cerebras inference), structured outputs
- **Market data**: Built-in GBM simulator (default) or Massive API (real data)

## Quick Start

```bash
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env

docker compose up -d
# Open http://localhost:8000
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for AI chat |
| `MASSIVE_API_KEY` | No | Massive API key for real market data; omit for simulator |
| `LLM_MOCK` | No | `true` for deterministic mock responses (testing) |

## Project Structure

```
finally/
  frontend/    # Next.js static export
  backend/     # FastAPI uv project
  planning/    # Design docs and agent contracts
  db/          # SQLite volume mount (runtime)
  scripts/     # Docker start/stop helpers
  test/        # Playwright E2E tests
```

## License

See [LICENSE](LICENSE).
