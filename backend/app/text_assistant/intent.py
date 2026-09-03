"""Small deterministic conversation classifier; it grants no authority."""

from dataclasses import dataclass

from backend.app.text_assistant.enums import AssistantIntent

_SAVE_PREFIXES = ("remember that ", "recuerda que ")
_RECALL_PREFIXES = (
    "what do you remember about ",
    "qué recuerdas sobre ",
    "que recuerdas sobre ",
)
_DELETE_PREFIXES = (
    "forget this",
    "olvida esto",
    "delete memory",
    "elimina esa memoria",
)
_ACTION_PREFIXES = (
    "send ",
    "envía ",
    "envia ",
    "schedule ",
    "programa ",
    "delete ",
    "elimina ",
    "buy ",
    "sell ",
    "transfer ",
    "withdraw ",
    "deposit ",
    "place order ",
    "change leverage ",
    "increase risk ",
    "compra ",
    "vende ",
    "transfiere ",
    "retira ",
    "deposita ",
    "i confirm buy ",
    "i confirm, buy ",
    "confirmo compra ",
)
_RESEARCH_PREFIXES = (
    "search ",
    "search for ",
    "research ",
    "look up ",
    "find online ",
    "read http://",
    "read https://",
    "fetch http://",
    "fetch https://",
    "busca ",
    "investiga ",
    "consulta en la web ",
    "lee http://",
    "lee https://",
    "abre http://",
    "abre https://",
)
_RESEARCH_MARKERS = (
    " latest ",
    " current ",
    " today ",
    " news ",
    " noticias ",
    " últimas ",
    " ultimas ",
    " actualmente ",
)


@dataclass(frozen=True, slots=True)
class ClassifiedIntent:
    kind: AssistantIntent
    payload: str | None = None


def classify_intent(content: str) -> ClassifiedIntent:
    """Recognize only explicit bounded commands; normal text remains conversation."""
    normalized = " ".join(content.casefold().split())
    for prefix in _SAVE_PREFIXES:
        if normalized.startswith(prefix):
            payload = content.strip()[len(prefix) :].strip()
            return ClassifiedIntent(AssistantIntent.MEMORY_SAVE, payload or None)
    for prefix in _RECALL_PREFIXES:
        if normalized.startswith(prefix):
            payload = content.strip()[len(prefix) :].strip()
            return ClassifiedIntent(AssistantIntent.MEMORY_RECALL, payload or None)
    if normalized.startswith(_DELETE_PREFIXES):
        return ClassifiedIntent(AssistantIntent.MEMORY_DELETE)
    if normalized.startswith(_ACTION_PREFIXES):
        return ClassifiedIntent(AssistantIntent.ACTION)
    padded = f" {normalized} "
    if normalized.startswith(_RESEARCH_PREFIXES) or any(
        marker in padded for marker in _RESEARCH_MARKERS
    ):
        return ClassifiedIntent(AssistantIntent.RESEARCH, content.strip())
    return ClassifiedIntent(AssistantIntent.CHAT)
