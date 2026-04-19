# Review Findings

## Findings

1. High - `backend/app/routes/watchlist.py:75` removes a ticker from the market provider whenever it is deleted from the watchlist, but `backend/app/routes/portfolio.py:72` only allows sells when the provider still has a live price for that ticker. That means a user can buy `AAPL`, remove `AAPL` from the watchlist, and then get blocked from selling the held position with `400 no live price ... add it to the watchlist first`. `backend/app/routes/portfolio.py:47` also falls back to `avg_cost` when the provider no longer tracks the symbol, so the UI stops showing live valuation for the held position as soon as it is removed from the watchlist.

2. Medium - `backend/app/main.py:115` returns `({"detail": "Not Found"}, 404)` from the SPA fallback instead of raising `HTTPException` or returning a proper `Response`. In FastAPI that tuple is serialized as a normal response body rather than setting the status code, so unmatched `/api/*` and `/_next/*` requests will be reported as `200 OK` once the static frontend is mounted.

3. Medium - `backend/app/routes/system.py:19` reports readiness failures in the JSON body, but it never sets a non-2xx status. A broken DB connection or missing market provider will still return HTTP 200 from `/readyz`, which makes the endpoint unusable for actual readiness checks in container orchestration.

## Notes

- Scope reviewed: current worktree changes since `HEAD`, including the new untracked backend/frontend/devops/E2E files.
- I updated the writable review file at `test/planning/REVIEW.md` in this session.
- I did not run the backend locally in this shell because the available Python environment here does not have the app dependencies installed (`fastapi` import failed). The findings above are based on direct source inspection.
