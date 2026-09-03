"""Small in-process TTL cache storing only bounded public retrieval results."""

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True, slots=True)
class CacheEntry[T]:
    value: T
    fresh: bool


class BoundedTTLCache[T]:
    def __init__(self, *, max_entries: int = 128, ttl_seconds: float = 300.0) -> None:
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("Cache bounds must be positive")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, T]] = OrderedDict()

    @staticmethod
    def key(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def get(self, key: str) -> CacheEntry[T] | None:
        item = self._items.get(key)
        if item is None:
            return None
        created, value = item
        if monotonic() - created > self.ttl_seconds:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return CacheEntry(value=value, fresh=True)

    def put(self, key: str, value: T) -> None:
        self._items[key] = (monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
