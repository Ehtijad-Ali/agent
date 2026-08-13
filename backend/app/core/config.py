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

    # --- AI (spec §14) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_timeout_seconds: int = 60

    # --- platform credentials (spec §29 -- never leave this process) ---
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    discord_bot_token: str = ""
    discord_application_id: str = ""

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
