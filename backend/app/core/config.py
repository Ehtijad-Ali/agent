"""Application settings (spec §35).

Everything is environment-driven. Nothing here has a production-safe default:
secrets default to empty and are validated at startup, so a misconfigured deploy
fails loudly instead of running with a predictable key.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # --- persistence ---
    # Optional so the engine-only endpoints can run before Postgres exists.
    # Anything touching conversations checks this and returns 503 if unset.
    database_url: str = ""
    redis_url: str = ""

    # --- secrets ---
    secret_key: str = ""
    jwt_secret: str = ""
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14
    pseudonym_salt: str = ""

    # --- scanning ---
    # The brief specifies twice-daily scans plus manual runs. Times are UTC
    # "HH:MM", comma separated. A non-zero scan_interval_seconds overrides them
    # with a fixed interval, which is only useful in development.
    scan_times: str = "09:00,21:00"
    scan_interval_seconds: int = 0

    # Where this backend is reachable from the public internet. Tracking links
    # are built from it, so a wrong value produces links that do not resolve.
    public_base_url: str = "http://localhost:8000"

    # The destination every reply points at, and how the brand is written in
    # prose. Configurable because it appears in text posted publicly: a wrong
    # value here is not a bug report, it is a published message.
    product_url: str = "https://www.all-bettors.com"
    product_label: str = "All-Bettors.com"

    # --- AI (spec §14) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    # CPU inference is slow; an agent step with a long prompt can take minutes.
    ollama_timeout_seconds: int = 600
    # Context window. Ollama's default is small enough to cut off tool results
    # without an error, so it is set explicitly.
    ollama_context: int = 8192

    # Which model serves the AI Agent and AI drafts: "ollama" or "groq".
    ai_provider: str = "ollama"
    # AI-written summaries and replies for new leads at or above this score.
    # Leads below it keep the instant template drafts; on a CPU-only server
    # spending a minute on an irrelevant message is the wrong trade.
    ai_draft_min_score: int = 40
    ai_drafts_per_scan: int = 25

    # --- AI agent (Groq) ---
    # The key never leaves this process: it is not sent to the browser, logged,
    # or written anywhere but this environment.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    # Model for the built-in web-search tool; must be one Groq offers it on.
    groq_search_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: int = 90
    # Hard limits on one agent task, so a confused model cannot loop forever
    # or burn through the account.
    agent_max_iterations: int = 12
    agent_max_seconds: int = 600
    agent_max_tokens_per_task: int = 200_000
    agent_daily_tasks_per_user: int = 200
    # Conversations older than this are deleted at startup; 0 keeps them.
    agent_retention_days: int = 90

    # --- platform credentials (spec §29 -- never leave this process) ---
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    discord_bot_token: str = ""
    discord_application_id: str = ""

    # Reddit app (https://www.reddit.com/prefs/apps, type "script").
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "signal-monitor/1.0 (by joinallbettors)"
    # YouTube Data API v3 key (Google Cloud console).
    youtube_api_key: str = ""
    # Dedicated Telegram account (https://my.telegram.org + scripts/telegram_login.py).
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_session: str = ""

    # n8n webhook that receives strong new leads after each scan, e.g.
    # http://127.0.0.1:5678/n8n/webhook/new-lead. Empty disables it.
    n8n_lead_webhook_url: str = ""
    lead_alert_min_score: int = 70

    # --- CORS (spec §38) ---
    frontend_url: str = "http://localhost:3000"
    cors_allowed_origins: str = "http://localhost:3000"

    n8n_base_url: str = ""
    n8n_webhook_secret: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """Exact origins only. `*` is rejected outright in production."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def has_database(self) -> bool:
        return bool(self.database_url)

    @property
    def scan_time_list(self) -> list[str]:
        """Configured scan times, normalised and de-duplicated."""
        seen: list[str] = []
        for raw in self.scan_times.split(","):
            value = raw.strip()
            if value and value not in seen:
                seen.append(value)
        return seen

    @field_validator("cors_allowed_origins")
    @classmethod
    def _reject_wildcard(cls, v: str, info) -> str:
        env = (info.data or {}).get("environment")
        if env == "production" and "*" in v:
            raise ValueError("CORS wildcard is not allowed in production (spec §38)")
        return v

    def validate_for_production(self) -> list[str]:
        """Return a list of misconfigurations rather than raising one at a time,
        so a bad deploy surfaces every problem in a single log line."""
        problems: list[str] = []
        if self.environment != "production":
            return problems
        for name in ("secret_key", "jwt_secret", "pseudonym_salt", "database_url"):
            if not getattr(self, name):
                problems.append(f"{name.upper()} must be set in production")
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be at least 32 characters")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
