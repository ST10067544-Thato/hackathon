"""Environment configuration.

Credentials live in the repository root ``.env`` like the other apps in this kit.
Nothing here is read at import time except the ``.env`` file itself, so tests can
override values with monkeypatch before ``Settings.load()`` is called.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]

ZERNIO_DEFAULT_BASE_URL = "https://zernio.com/api/v1"


def load_env_files() -> None:
    """Load root ``.env`` first, then an app-local one; existing env vars win."""
    for candidate in (REPO_ROOT / ".env", APP_DIR / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


@dataclass(frozen=True)
class Settings:
    model_provider: str
    model_id: str
    openai_api_key: str | None
    openrouter_api_key: str | None
    exa_api_key: str | None
    zernio_api_key: str | None
    zernio_base_url: str
    zernio_webhook_secret: str | None
    zernio_profile_id: str | None
    database_url: str | None
    sqlite_path: Path
    host: str
    port: int
    browser_scout: str  # "auto" | "on" | "off"
    browser_headless: bool
    browser_max_steps: int
    browser_timeout_seconds: float
    browser_use_api_key: str | None
    browser_use_cloud: bool
    browser_model_id: str

    @classmethod
    def load(cls) -> "Settings":
        load_env_files()
        provider = (os.getenv("MODEL_PROVIDER") or "openai").strip().lower()
        default_model = "openai/gpt-5.4-mini" if provider == "openrouter" else "gpt-5.4-mini"
        return cls(
            model_provider=provider,
            model_id=(os.getenv("MODEL") or default_model).strip(),
            openai_api_key=_opt("OPENAI_API_KEY"),
            openrouter_api_key=_opt("OPENROUTER_API_KEY"),
            exa_api_key=_opt("EXA_API_KEY"),
            zernio_api_key=_opt("ZERNIO_API_KEY"),
            zernio_base_url=(os.getenv("ZERNIO_API_BASE_URL") or ZERNIO_DEFAULT_BASE_URL).rstrip("/"),
            zernio_webhook_secret=_opt("ZERNIO_WEBHOOK_SECRET"),
            zernio_profile_id=_opt("ZERNIO_PROFILE_ID"),
            database_url=_opt("DATABASE_URL"),
            sqlite_path=Path(os.getenv("CREATOR_COMPANION_DB") or APP_DIR / "data" / "creator-companion.db"),
            host=os.getenv("CREATOR_COMPANION_HOST") or "0.0.0.0",
            port=int(os.getenv("CREATOR_COMPANION_PORT") or "7777"),
            browser_scout=(os.getenv("BROWSER_SCOUT") or "auto").strip().lower(),
            browser_headless=(os.getenv("BROWSER_HEADLESS") or "1").strip().lower() not in ("0", "false", "no"),
            browser_max_steps=int(os.getenv("BROWSER_MAX_STEPS") or "12"),
            browser_timeout_seconds=float(os.getenv("BROWSER_TIMEOUT_SECONDS") or "180"),
            browser_use_api_key=_opt("BROWSER_USE_API_KEY"),
            browser_use_cloud=(os.getenv("BROWSER_USE_CLOUD") or "0").strip().lower() in ("1", "true", "yes"),
            browser_model_id=(os.getenv("BROWSER_MODEL") or os.getenv("MODEL") or default_model).strip(),
        )

    @property
    def model_api_key(self) -> str | None:
        return self.openrouter_api_key if self.model_provider == "openrouter" else self.openai_api_key


def _opt(name: str) -> str | None:
    value = os.getenv(name)
    value = value.strip() if value else ""
    return value or None
