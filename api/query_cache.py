"""Small TTL + LRU cache for identical /districts query strings (stdlib only)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict


class BytesTTLCache:
    """Thread-safe LRU of UTF-8 JSON bodies with per-entry TTL."""

    def __init__(self, *, max_entries: int, ttl_seconds: float, max_entry_bytes: int) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._max_entry_bytes = max_entry_bytes
        self._data: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            inserted, payload = item
            if now - inserted > self._ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return payload

    def set(self, key: str, payload: bytes) -> None:
        if len(payload) > self._max_entry_bytes:
            return
        now = time.monotonic()
        with self._lock:
            self._data[key] = (now, payload)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)
