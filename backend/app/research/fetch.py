"""Bounded pinned-IP HTTP retrieval with per-redirect safety validation."""

import asyncio
import http.client
import socket
import ssl
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

from backend.app.research.enums import ResearchErrorCode
from backend.app.research.errors import ResearchError
from backend.app.research.policy import ResearchBudget
from backend.app.research.url_safety import ResolvedTarget, URLSafetyPolicy


@dataclass(frozen=True, slots=True)
class RawFetchResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class HttpTransport(Protocol):
    async def request(
        self, target: ResolvedTarget, *, max_bytes: int, timeout: float
    ) -> RawFetchResponse: ...


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, target: ResolvedTarget, timeout: float) -> None:
        super().__init__(target.host, target.port, timeout=timeout)
        self._pinned_ip = target.pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, target: ResolvedTarget, timeout: float) -> None:
        self._ssl_context = ssl.create_default_context()
        super().__init__(target.host, target.port, timeout=timeout, context=self._ssl_context)
        self._pinned_ip = target.pinned_ip

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._ssl_context.wrap_socket(raw, server_hostname=self.host)


class PinnedHttpTransport:
    async def request(
        self, target: ResolvedTarget, *, max_bytes: int, timeout: float
    ) -> RawFetchResponse:
        return await asyncio.to_thread(self._request_sync, target, max_bytes, timeout)

    @staticmethod
    def _request_sync(target: ResolvedTarget, max_bytes: int, timeout: float) -> RawFetchResponse:
        connection: http.client.HTTPConnection
        if target.scheme == "https":
            connection = _PinnedHTTPSConnection(target, timeout)
        else:
            connection = _PinnedHTTPConnection(target, timeout)
        try:
            connection.request(
                "GET",
                target.path_and_query,
                headers={
                    "Host": target.host,
                    "User-Agent": "PersonalAssistantResearch/0.13",
                    "Accept": "text/html,text/plain;q=0.9",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            headers = {key.casefold(): value for key, value in response.getheaders()}
            length = headers.get("content-length")
            if length is not None and int(length) > max_bytes:
                raise ResearchError(ResearchErrorCode.CONTENT_TOO_LARGE)
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ResearchError(ResearchErrorCode.CONTENT_TOO_LARGE)
            return RawFetchResponse(response.status, headers, body)
        except ResearchError:
            raise
        except TimeoutError:
            raise ResearchError(ResearchErrorCode.FETCH_TIMEOUT) from None
        except (OSError, http.client.HTTPException, ValueError):
            raise ResearchError(ResearchErrorCode.PROVIDER_UNAVAILABLE) from None
        finally:
            connection.close()


class SafeFetcher:
    def __init__(
        self,
        safety: URLSafetyPolicy,
        *,
        transport: HttpTransport | None = None,
        budget: ResearchBudget | None = None,
    ) -> None:
        self.safety = safety
        self.transport = transport or PinnedHttpTransport()
        self.budget = budget or ResearchBudget()

    async def fetch(self, raw_url: str) -> tuple[str, str, bytes]:
        current = raw_url
        history: dict[str, tuple[str, ...]] = {}
        for redirect_index in range(self.budget.max_redirects + 1):
            target = self.safety.resolve_target(current, resolution_history=history)
            try:
                response = await asyncio.wait_for(
                    self.transport.request(
                        target,
                        max_bytes=self.budget.max_response_bytes,
                        timeout=self.budget.fetch_timeout_seconds,
                    ),
                    timeout=self.budget.fetch_timeout_seconds,
                )
            except TimeoutError:
                raise ResearchError(ResearchErrorCode.FETCH_TIMEOUT) from None
            encoding = response.headers.get("content-encoding", "identity").casefold()
            if encoding not in {"", "identity"}:
                raise ResearchError(ResearchErrorCode.UNSUPPORTED_CONTENT)
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location or redirect_index >= self.budget.max_redirects:
                    raise ResearchError(ResearchErrorCode.BLOCKED_URL)
                current = urljoin(target.canonical_url, location)
                continue
            if response.status == 429:
                raise ResearchError(ResearchErrorCode.RATE_LIMITED)
            if not 200 <= response.status < 300:
                raise ResearchError(ResearchErrorCode.PROVIDER_UNAVAILABLE)
            content_type = response.headers.get("content-type", "").casefold()
            if not content_type.startswith(("text/html", "text/plain")):
                raise ResearchError(ResearchErrorCode.UNSUPPORTED_CONTENT)
            return target.canonical_url, content_type, response.body
        raise ResearchError(ResearchErrorCode.BLOCKED_URL)
