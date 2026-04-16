from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import orjson

_LOGGER = logging.getLogger("hilti.map_api.profile")


def profiling_enabled() -> bool:
    return os.getenv("HILTI_PROFILE_MAP_API", "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ProfileStage:
    name: str
    elapsed_ms: float
    rows_before: int | None = None
    rows_after: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class RequestProfile:
    def __init__(self, route: str, *, params: dict[str, Any] | None = None, enabled: bool | None = None) -> None:
        self.enabled = profiling_enabled() if enabled is None else enabled
        self.route = route
        self.params = params or {}
        self.request_id = uuid.uuid4().hex[:10]
        self._started = time.perf_counter()
        self._stages: list[ProfileStage] = []
        self._caches: dict[str, dict[str, Any]] = {}
        self._summary: dict[str, Any] = {}

    @contextmanager
    def stage(
        self,
        name: str,
        *,
        rows_before: int | None = None,
        rows_after_default: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Iterator["StageHandle"]:
        if not self.enabled:
            yield StageHandle.disabled()
            return
        started = time.perf_counter()
        handle = StageHandle(rows_after=rows_after_default, meta=dict(meta or {}))
        try:
            yield handle
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self._stages.append(
                ProfileStage(
                    name=name,
                    elapsed_ms=elapsed_ms,
                    rows_before=rows_before,
                    rows_after=handle.rows_after,
                    meta=handle.meta,
                )
            )

    def add_stage(
        self,
        name: str,
        *,
        elapsed_ms: float = 0.0,
        rows_before: int | None = None,
        rows_after: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        self._stages.append(
            ProfileStage(
                name=name,
                elapsed_ms=elapsed_ms,
                rows_before=rows_before,
                rows_after=rows_after,
                meta=dict(meta or {}),
            )
        )

    def cache(self, name: str, status: str, **meta: Any) -> None:
        if not self.enabled:
            return
        payload = {"status": status}
        payload.update(meta)
        self._caches[name] = payload

    def set_summary(self, **fields: Any) -> None:
        if not self.enabled:
            return
        self._summary.update(fields)

    def finish(self, *, response_bytes: int | None = None, status_code: int = 200, extra: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        total_ms = (time.perf_counter() - self._started) * 1000.0
        payload = {
            "event": "map_api_profile",
            "request_id": self.request_id,
            "route": self.route,
            "status_code": status_code,
            "total_ms": round(total_ms, 3),
            "response_bytes": response_bytes,
            "params": self.params,
            "caches": self._caches,
            "stages": [
                {
                    "name": stage.name,
                    "elapsed_ms": round(stage.elapsed_ms, 3),
                    "rows_before": stage.rows_before,
                    "rows_after": stage.rows_after,
                    "meta": stage.meta,
                }
                for stage in self._stages
            ],
            "summary": self._summary,
        }
        if extra:
            payload.update(extra)
        _LOGGER.info(orjson.dumps(payload).decode("utf-8"))


@dataclass
class StageHandle:
    rows_after: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> "StageHandle":
        return cls()

    def set_rows_after(self, rows_after: int | None) -> None:
        self.rows_after = rows_after

    def update_meta(self, **meta: Any) -> None:
        self.meta.update(meta)
