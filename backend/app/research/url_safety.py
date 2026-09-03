"""Canonical URL and DNS boundary preventing SSRF, rebinding, and redirect escape."""

import ipaddress
import posixpath
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from backend.app.research.enums import ResearchErrorCode
from backend.app.research.errors import ResearchError

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)
_TRACKING = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    canonical_url: str
    scheme: str
    host: str
    port: int
    path_and_query: str
    addresses: tuple[str, ...]
    pinned_ip: str


class SystemResolver:
    def resolve(self, host: str, port: int) -> tuple[str, ...]:
        try:
            results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, OSError):
            raise ResearchError(ResearchErrorCode.BLOCKED_URL) from None
        return tuple(sorted({str(item[4][0]) for item in results}))


class URLSafetyPolicy:
    def __init__(self, resolver: SystemResolver | None = None) -> None:
        self.resolver = resolver or SystemResolver()

    @staticmethod
    def canonicalize(raw_url: str) -> str:
        if not raw_url or len(raw_url) > 4096 or any(ord(char) < 32 for char in raw_url):
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        try:
            parsed = urlsplit(raw_url.strip())
            port = parsed.port
        except ValueError:
            raise ResearchError(ResearchErrorCode.BLOCKED_URL) from None
        scheme = parsed.scheme.casefold()
        if (
            scheme not in {"http", "https"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        if not parsed.hostname:
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        try:
            host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()
        except UnicodeError:
            raise ResearchError(ResearchErrorCode.BLOCKED_URL) from None
        if (
            host in _BLOCKED_HOSTS
            or host.endswith((".localhost", ".local", ".internal", ".home", ".lan"))
            or "." not in host
            or host.isdecimal()
        ):
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        expected_port = 443 if scheme == "https" else 80
        if port not in {None, expected_port}:
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        path = quote(posixpath.normpath(parsed.path or "/"), safe="/%:@-._~!$&'()*+,;=")
        if parsed.path.endswith("/") and not path.endswith("/"):
            path += "/"
        pairs = sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
            if key.casefold() not in _TRACKING and not key.casefold().startswith("utm_")
        )
        netloc = f"[{host}]" if ":" in host else host
        return urlunsplit((scheme, netloc, path, urlencode(pairs, doseq=True), ""))

    def resolve_target(
        self,
        raw_url: str,
        *,
        resolution_history: dict[str, tuple[str, ...]] | None = None,
    ) -> ResolvedTarget:
        canonical = self.canonicalize(raw_url)
        parsed = urlsplit(canonical)
        host = parsed.hostname
        if host is None:
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        port = 443 if parsed.scheme == "https" else 80
        addresses = self.resolver.resolve(host, port)
        if not addresses:
            raise ResearchError(ResearchErrorCode.BLOCKED_URL)
        normalized: list[str] = []
        for raw_address in addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError:
                raise ResearchError(ResearchErrorCode.BLOCKED_URL) from None
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            ):
                raise ResearchError(ResearchErrorCode.BLOCKED_URL)
            normalized.append(str(address))
        normalized_addresses = tuple(sorted(set(normalized)))
        if resolution_history is not None:
            previous = resolution_history.get(host)
            if previous is not None and previous != normalized_addresses:
                raise ResearchError(ResearchErrorCode.DNS_REBINDING)
            resolution_history[host] = normalized_addresses
        path_and_query = parsed.path or "/"
        if parsed.query:
            path_and_query += f"?{parsed.query}"
        return ResolvedTarget(
            canonical_url=canonical,
            scheme=parsed.scheme,
            host=host,
            port=port,
            path_and_query=path_and_query,
            addresses=normalized_addresses,
            pinned_ip=normalized_addresses[0],
        )
