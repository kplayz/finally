"""Background tasks: portfolio snapshots every 30s, pruning >24h old."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from db import get_conn, iso_now
from .portfolio import compute_total_value

log = logging.getLogger(__name__)


def record_snapshot(conn: sqlite3.Connection, user_id: str, total_value: float) -> None:
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, float(total_value), iso_now()),
    )


def prune_old_snapshots(conn: sqlite3.Connection, retention_hours: int = 24) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    res = conn.execute(
        "DELETE FROM portfolio_snapshots WHERE recorded_at < ?", (cutoff,)
    )
    return res.rowcount


async def snapshot_loop(
    get_provider,
    interval_s: int = 30,
    retention_hours: int = 24,
    user_id: str = "default",
) -> None:
    """Write a portfolio snapshot every ``interval_s`` seconds and prune."""
    while True:
        try:
            provider = get_provider()

            def lookup(t: str) -> float | None:
                if provider is None:
                    return None
                p = provider.get_price(t)
                return p.price if p else None

            with get_conn() as conn:
                total = compute_total_value(conn, user_id, lookup)
                record_snapshot(conn, user_id, total)
                prune_old_snapshots(conn, retention_hours)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("snapshot_loop iteration failed")
        await asyncio.sleep(interval_s)
