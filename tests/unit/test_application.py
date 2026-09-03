"""Application construction tests."""

from fastapi import FastAPI

from backend.app.core.config import Environment, Settings
from backend.app.main import create_app


def test_application_can_be_created() -> None:
    settings = Settings(environment=Environment.LOCAL)

    application = create_app(settings)

    assert isinstance(application, FastAPI)
    assert application.title == "personal-assistant-backend"
    assert application.version == "0.13.0"
