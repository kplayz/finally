# Review Findings

## High

1. `backend/app/main.py:115-127` breaks API 404 behavior whenever static assets are present. The catch-all `/{full_path:path}` route tries to "let FastAPI's 404 surface", but it returns `({"detail": "Not Found"}, 404)` instead of raising/returning a real 404 response. In FastAPI that tuple is serialized as a normal 200 response, so unknown API paths like `/api/does-not-exist` stop reporting 404s once the frontend is built.

2. `backend/app/routes/watchlist.py:75-90`, `backend/app/routes/portfolio.py:72-80`, and `backend/app/llm/handler.py:101-108` strand open positions when a ticker is removed from the watchlist. Removing the symbol immediately evicts it from the market provider, but both manual and chat-driven sells require a live cached price. After removing a held ticker, the position freezes at `avg_cost` in portfolio views and cannot be sold until the symbol is re-added and repriced.

## Medium

3. `backend/app/routes/watchlist.py:56-72` does not implement the invalid-ticker rejection required by `planning/PLAN.md:189-191`, even though `backend/market/massive.py:33-35,82-97` already documents and provides `validate_ticker()`. In Massive mode the API currently persists any symbol and returns success, leaving bad tickers in the DB and poll set instead of failing the add request.

4. `.claude/agents/llm-engineer.md:11` requires the `llm-engineer` agent to invoke a `cerebras` skill, but the repository defines `.claude/skills/cerebras/SKILL.md:2` as `cerebras-inference`, and `planning/PLAN.md:345-356` uses that same name. As written, the agent instructions point at a non-existent prerequisite.

5. `.claude/agents/devops-engineer.md:32-33` is internally inconsistent. Line 32 forbids modifying anything under `planning/`, then line 33 instructs the same agent to write requests to `planning/DEVOPS_REQUESTS.md`. That makes the documented escalation path self-contradictory.

## Notes

- I reviewed the tracked diff versus `HEAD` and the new untracked project files that make up the current change set.
- I could not run the backend tests in this sandbox because `uv` could not initialize its cache, and the frontend/Playwright suites failed with `spawn EPERM` before test execution. Those environment failures are not included as product findings.
