"""Server-owned Web Research mode, privacy, and budget policy."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from backend.app.orchestrator.enums import SafeMode
from backend.app.research.enums import ResearchMode
from backend.app.security.classification import DataSensitivity, sensitivity_rank

POLICY_VERSION = "web-research-v1"
_URL = re.compile(r"https?://[^\s<>{}\[\]\"']+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)")
_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
_LEADING = re.compile(
    r"^(?:search(?: for)?|research|look up|find online|busca|investiga|consulta en (?:la )?web)\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ResearchBudget:
    max_search_calls: int = 2
    max_fetches: int = 5
    max_sources: int = 5
    max_redirects: int = 3
    max_response_bytes: int = 1_000_000
    max_total_bytes: int = 3_000_000
    max_extracted_chars: int = 200_000
    max_evidence_items: int = 8
    max_provider_attempts: int = 2
    fetch_timeout_seconds: float = 8.0
    total_timeout_seconds: float = 20.0


class ResearchPolicy:
    def __init__(
        self,
        *,
        enabled: bool,
        safe_mode: SafeMode,
        budget: ResearchBudget | None = None,
    ) -> None:
        self.enabled = enabled
        self.safe_mode = safe_mode
        self.budget = budget or ResearchBudget()

    def permits_external_access(self, sensitivity: DataSensitivity) -> bool:
        return (
            self.enabled
            and self.safe_mode is SafeMode.NORMAL
            and sensitivity_rank(sensitivity) < sensitivity_rank(DataSensitivity.SENSITIVE)
        )

    @staticmethod
    def select_mode(content: str) -> ResearchMode:
        normalized = " ".join(content.casefold().split())
        urls = _URL.findall(content)
        if urls and any(
            marker in normalized
            for marker in ("read ", "fetch ", "open ", "lee ", "abre ", "resume ")
        ):
            return ResearchMode.FETCH
        if any(
            marker in normalized
            for marker in (
                "research ",
                "investiga ",
                "compare sources",
                "multiple sources",
                "varias fuentes",
                "fuentes distintas",
            )
        ):
            return ResearchMode.MULTI_SOURCE_RESEARCH
        if any(
            marker in normalized
            for marker in (
                "search ",
                "look up ",
                "find online ",
                "busca ",
                "consulta en la web",
                "latest ",
                "current ",
                "today ",
                "últim",
                "actual",
                "hoy ",
                "news ",
                "noticias ",
            )
        ):
            return ResearchMode.SEARCH
        return ResearchMode.NO_RESEARCH

    @staticmethod
    def direct_url(content: str) -> str | None:
        match = _URL.search(content)
        return match.group(0).rstrip(".,;:!?)") if match else None

    @staticmethod
    def minimize_query(content: str) -> str:
        value = _LEADING.sub("", " ".join(content.split())).strip()
        value = _URL.sub(lambda match: urlsplit(match.group(0)).hostname or "[url]", value)
        value = _EMAIL.sub("[email]", value)
        value = _PHONE.sub("[phone]", value)
        value = _TOKEN.sub("[token]", value)
        return value[:500].strip()
