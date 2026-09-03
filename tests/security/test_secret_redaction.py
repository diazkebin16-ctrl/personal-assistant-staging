"""Secret-redaction security foundation tests."""

import json

from backend.app.core.redaction import REDACTED, redact_secrets, redact_text


def test_sensitive_mapping_fields_are_redacted_recursively() -> None:
    payload = {
        "password": "correct-horse",
        "nested": {
            "api_key": "api-value",
            "apiKey": "camel-api-value",
            "service_role_key": "role-value",
            "safe": "visible",
        },
        "authorization": "Bearer bearer-value",
    }

    result = redact_secrets(payload)
    rendered = json.dumps(result)

    assert result["password"] == REDACTED
    assert result["nested"]["safe"] == "visible"
    assert "correct-horse" not in rendered
    assert "api-value" not in rendered
    assert "camel-api-value" not in rendered
    assert "role-value" not in rendered
    assert "bearer-value" not in rendered


def test_sensitive_values_are_redacted_from_text() -> None:
    value = 'token="token-value" authorization=Bearer-value Bearer raw-bearer-value'

    result = redact_text(value)

    assert "token-value" not in result
    assert "Bearer-value" not in result
    assert "raw-bearer-value" not in result
    assert REDACTED in result


def test_phase1_authentication_fields_and_private_keys_are_redacted() -> None:
    payload = {
        "access_token": "access-value",
        "refreshToken": "refresh-value",
        "jwt": "jwt-value",
        "private_key": "private-value",
        "safe": "visible",
    }

    result = redact_secrets(payload)
    rendered = json.dumps(result)

    assert result["safe"] == "visible"
    assert "access-value" not in rendered
    assert "refresh-value" not in rendered
    assert "jwt-value" not in rendered
    assert "private-value" not in rendered
