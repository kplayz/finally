#!/usr/bin/env bash
# Stop FinAlly. Does NOT remove the data volume.

set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
echo "[stop] Container stopped. Volume 'finally-data' preserved."
