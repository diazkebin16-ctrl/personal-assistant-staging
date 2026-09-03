"""Central settings validation tests."""

import pytest
from pydantic import ValidationError

from backend.app.core.config import Environment, Settings


def test_valid_environment_is_accepted() -> None:
    settings = Settings.model_validate({"ENVIRONMENT": "staging"})

    assert settings.environment is Environment.STAGING


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"ENVIRONMENT": "qa"})


def test_supabase_url_derives_strict_issuer_and_jwks_endpoint() -> None:
    settings = Settings.model_validate({"SUPABASE_URL": "https://project-id.supabase.co"})

    assert settings.effective_jwt_issuer == "https://project-id.supabase.co/auth/v1"
    assert (
        settings.effective_jwks_url
        == "https://project-id.supabase.co/auth/v1/.well-known/jwks.json"
    )


def test_invalid_jwks_cache_ttl_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"AUTH_JWKS_CACHE_TTL": 30})
