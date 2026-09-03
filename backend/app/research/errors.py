"""Safe typed failures that never expose provider or network internals."""

from uuid import UUID

from backend.app.research.enums import ResearchErrorCode


class ResearchError(Exception):
    def __init__(self, code: ResearchErrorCode, *, confirmation_id: UUID | None = None) -> None:
        super().__init__(code.value)
        self.code = code
        self.confirmation_id = confirmation_id
