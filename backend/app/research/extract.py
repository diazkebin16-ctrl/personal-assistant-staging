"""Deterministic text extraction that excludes active and hidden HTML content."""

from html.parser import HTMLParser

from backend.app.research.enums import ResearchErrorCode
from backend.app.research.errors import ResearchError

_IGNORED = frozenset({"script", "style", "noscript", "template", "svg", "canvas"})


class _VisibleTextParser(HTMLParser):
    def __init__(self, max_chars: int) -> None:
        super().__init__(convert_charrefs=True)
        self.max_chars = max_chars
        self.ignored_depth = 0
        self.hidden_depth = 0
        self._hidden_stack: list[bool] = []
        self._title_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): (value or "").casefold() for key, value in attrs}
        if tag.casefold() in _IGNORED:
            self.ignored_depth += 1
        hidden = (
            "hidden" in values
            or values.get("aria-hidden") == "true"
            or "display:none" in values.get("style", "").replace(" ", "")
            or "visibility:hidden" in values.get("style", "").replace(" ", "")
        )
        self._hidden_stack.append(hidden)
        if hidden:
            self.hidden_depth += 1
        if tag.casefold() == "title":
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in _IGNORED and self.ignored_depth:
            self.ignored_depth -= 1
        hidden = self._hidden_stack.pop() if self._hidden_stack else False
        if hidden and self.hidden_depth:
            self.hidden_depth -= 1
        if tag.casefold() == "title" and self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.ignored_depth or self.hidden_depth:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._title_depth:
            self.title_parts.append(value)
        if sum(len(item) for item in self.parts) < self.max_chars:
            self.parts.append(value)


def extract_document(body: bytes, content_type: str, *, max_chars: int) -> tuple[str, str]:
    if not body:
        raise ResearchError(ResearchErrorCode.EXTRACTION_FAILED)
    if not content_type.startswith(("text/html", "text/plain")):
        raise ResearchError(ResearchErrorCode.UNSUPPORTED_CONTENT)
    charset = "utf-8"
    for segment in content_type.split(";")[1:]:
        key, _, value = segment.strip().partition("=")
        if key == "charset":
            charset = value.strip('"').casefold()
    if charset not in {"utf-8", "utf8", "us-ascii", "iso-8859-1"}:
        raise ResearchError(ResearchErrorCode.UNSUPPORTED_CONTENT)
    try:
        decoded = body.decode(charset, errors="replace")
    except LookupError:
        raise ResearchError(ResearchErrorCode.UNSUPPORTED_CONTENT) from None
    if content_type.startswith("text/plain"):
        text = " ".join(decoded.split())[:max_chars]
        if not text:
            raise ResearchError(ResearchErrorCode.EXTRACTION_FAILED)
        return "Untitled source", text
    parser = _VisibleTextParser(max_chars)
    try:
        parser.feed(decoded)
        parser.close()
    except Exception:
        raise ResearchError(ResearchErrorCode.EXTRACTION_FAILED) from None
    text = " ".join(parser.parts)[:max_chars].strip()
    title = " ".join(parser.title_parts)[:500].strip() or "Untitled source"
    if not text:
        raise ResearchError(ResearchErrorCode.EXTRACTION_FAILED)
    return title, text
