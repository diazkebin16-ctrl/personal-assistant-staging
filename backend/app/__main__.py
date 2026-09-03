"""Local and Railway-compatible backend entry point."""

import uvicorn

from backend.app.core.config import get_settings


def run() -> None:
    """Start the ASGI server using centrally validated settings."""
    settings = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",  # noqa: S104 - required for container/network deployment.
        log_config=None,
        port=settings.port,
    )


if __name__ == "__main__":
    run()
