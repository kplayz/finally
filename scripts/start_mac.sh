#!/usr/bin/env bash
# Start FinAlly locally via docker compose. Idempotent.
#   --build : force rebuild
#   --open  : open http://localhost:8000 in the default browser

set -euo pipefail

cd "$(dirname "$0")/.."

BUILD_FLAG=""
OPEN_BROWSER="false"
for arg in "$@"; do
  case "$arg" in
    --build) BUILD_FLAG="--build" ;;
    --open)  OPEN_BROWSER="true" ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
  esac
done

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "[start] .env was missing — copied from .env.example. Fill in OPENROUTER_API_KEY."
  else
    echo "[start] .env missing and no .env.example to copy from." >&2
    exit 1
  fi
fi

echo "[start] Bringing up FinAlly..."
docker compose up -d $BUILD_FLAG

URL="http://localhost:8000"
echo "[start] Waiting for health at ${URL}/api/health..."
for i in {1..60}; do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    echo "[start] Ready at ${URL}"
    if [[ "$OPEN_BROWSER" == "true" ]]; then
      if command -v open >/dev/null 2>&1; then open "$URL"
      elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
      fi
    fi
    exit 0
  fi
  sleep 1
done

echo "[start] Timed out waiting for health. Check: docker compose logs -f" >&2
exit 1
