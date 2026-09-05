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


def test_openai_api_key_is_optional_secret_and_blank_is_unconfigured() -> None:
    marker = "openai-key-marker-not-for-repr"
    configured = Settings.model_validate({"OPENAI_API_KEY": marker})
    blank = Settings.model_validate({"OPENAI_API_KEY": "   "})
    assert configured.openai_api_key is not None
    assert configured.openai_api_key.get_secret_value() == marker
    assert marker not in repr(configured)
    assert blank.openai_api_key is None


def test_gemini_configuration_is_not_part_of_settings_contract() -> None:
    assert "gemini_api_key" not in Settings.model_fields
