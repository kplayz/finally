"""Runtime configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    massive_api_key: str
    llm_model: str
    llm_mock: bool
    db_path: Path
    static_dir: Path | None
    snapshot_interval_s: int = 30
    snapshot_retention_hours: int = 24
    sse_cadence_ms: int = 500


def load_settings() -> Settings:
    """Read settings fresh from the environment. Call once at startup."""
    default_db = Path(__file__).resolve().parents[2] / "db" / "finally.db"
    db_path = Path(os.environ.get("FINALLY_DB_PATH") or default_db)

    # In Docker, static lives at /app/backend/static. Locally, it may be
    # frontend/out. We serve whichever exists; otherwise none.
    candidates = [
        Path(os.environ["FINALLY_STATIC_DIR"]) if os.environ.get("FINALLY_STATIC_DIR") else None,
        Path(__file__).resolve().parent.parent / "static",
        Path(__file__).resolve().parents[2] / "frontend" / "out",
    ]
    static_dir = next((p for p in candidates if p and p.is_dir()), None)

    return Settings(
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", "").strip(),
        massive_api_key=os.environ.get("MASSIVE_API_KEY", "").strip(),
        llm_model=os.environ.get("LLM_MODEL", "openrouter/openai/gpt-oss-120b").strip(),
        llm_mock=_bool("LLM_MOCK", default=False),
        db_path=db_path,
        static_dir=static_dir,
    )
