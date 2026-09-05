"""Central, validated application configuration."""

from enum import StrEnum
from functools import lru_cache
from typing import Any, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported deployment environments."""

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        populate_by_name=True,
        extra="ignore",
    )

    app_name: str = Field(default="personal-assistant-backend", validation_alias="APP_NAME")
    app_version: str = Field(default="0.13.0", validation_alias="APP_VERSION")
    environment: Environment = Field(default=Environment.LOCAL, validation_alias="ENVIRONMENT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    supabase_url: AnyHttpUrl | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_anon_key: SecretStr | None = Field(default=None, validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: SecretStr | None = Field(
        default=None, validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    sentry_dsn: SecretStr | None = Field(default=None, validation_alias="SENTRY_DSN")
    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    supabase_jwt_audience: str = Field(
        default="authenticated",
        min_length=1,
        max_length=128,
        validation_alias="SUPABASE_JWT_AUDIENCE",
    )
    supabase_jwt_issuer: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="SUPABASE_JWT_ISSUER",
    )
    supabase_jwks_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="SUPABASE_JWKS_URL",
    )
    auth_jwks_cache_ttl: int = Field(
        default=600,
        ge=60,
        le=3600,
        validation_alias="AUTH_JWKS_CACHE_TTL",
    )
    auth_jwks_timeout_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=10.0,
        validation_alias="AUTH_JWKS_TIMEOUT_SECONDS",
    )
    port: int = Field(default=8000, ge=1, le=65535, validation_alias="PORT")
    orchestrator_mode: Literal["NORMAL", "SAFE_MODE", "MAINTENANCE"] = Field(
        default="NORMAL", validation_alias="ORCHESTRATOR_MODE"
    )
    orchestrator_ai_enabled: bool = Field(default=True, validation_alias="ORCHESTRATOR_AI_ENABLED")
    orchestrator_actions_enabled: bool = Field(
        default=True, validation_alias="ORCHESTRATOR_ACTIONS_ENABLED"
    )
    research_enabled: bool = Field(default=False, validation_alias="RESEARCH_ENABLED")
    voice_credential_ttl_seconds: int = Field(
        default=120,
        ge=30,
        le=300,
        validation_alias="VOICE_CREDENTIAL_TTL_SECONDS",
    )
    voice_connection_timeout_seconds: int = Field(
        default=10,
        ge=5,
        le=30,
        validation_alias="VOICE_CONNECTION_TIMEOUT_SECONDS",
    )
    voice_idle_timeout_seconds: int = Field(
        default=45,
        ge=15,
        le=300,
        validation_alias="VOICE_IDLE_TIMEOUT_SECONDS",
    )
    voice_max_session_seconds: int = Field(
        default=900,
        ge=60,
        le=3600,
        validation_alias="VOICE_MAX_SESSION_SECONDS",
    )
    voice_max_reconnect_attempts: int = Field(
        default=3,
        ge=0,
        le=3,
        validation_alias="VOICE_MAX_RECONNECT_ATTEMPTS",
    )
    voice_profile: str = Field(
        default="calm-professional-v1",
        min_length=2,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
        validation_alias="VOICE_PROFILE",
    )

    @field_validator(
        "database_url",
        "supabase_url",
        "supabase_anon_key",
        "supabase_service_role_key",
        "openai_api_key",
        "sentry_dsn",
        "supabase_jwt_issuer",
        "supabase_jwks_url",
        mode="before",
    )
    @classmethod
    def empty_optional_value_is_none(cls, value: Any) -> Any:
        """Treat intentionally blank optional integrations as unconfigured."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def effective_jwt_issuer(self) -> str | None:
        """Return the explicit issuer or derive it from the Supabase project URL."""
        if self.supabase_jwt_issuer is not None:
            return str(self.supabase_jwt_issuer).rstrip("/")
        if self.supabase_url is None:
            return None
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1"

    @property
    def effective_jwks_url(self) -> str | None:
        """Return the explicit JWKS URL or derive the Supabase discovery endpoint."""
        if self.supabase_jwks_url is not None:
            return str(self.supabase_jwks_url)
        issuer = self.effective_jwt_issuer
        if issuer is None:
            return None
        return f"{issuer}/.well-known/jwks.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache the validated runtime configuration."""
    return Settings()
