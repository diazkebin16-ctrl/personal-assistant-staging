"""Structured logging configuration with secret redaction."""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from backend.app.core.config import Settings
from backend.app.core.redaction import redact_secrets, redact_text

_CONTEXT_FIELDS = (
    "trace_id",
    "task_id",
    "execution_id",
    "user_id",
    "device_id",
    "capability_key",
    "risk_level",
    "decision_id",
    "provider_key",
    "model_id",
    "model_class",
    "retry_count",
    "fallback_count",
    "estimated_cost_microunits",
)


class StructuredJsonFormatter(logging.Formatter):
    """Render stable JSON logs that can later carry tracing context."""

    def __init__(self, environment: str) -> None:
        super().__init__()
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._safe_message(record),
            "environment": self.environment,
        }

        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = redact_secrets(value)

        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))

        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _safe_message(record: logging.LogRecord) -> str:
        if isinstance(record.msg, (Mapping, list, tuple)):
            return json.dumps(redact_secrets(record.msg), ensure_ascii=False, default=str)
        return redact_text(record.getMessage())


def configure_logging(settings: Settings) -> None:
    """Configure root logging once per application instance."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter(str(settings.environment)))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.log_level))
    logging.captureWarnings(True)
