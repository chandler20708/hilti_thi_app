"""Single-entry cache of the full scored GeoDataFrame (expensive THI pass).

One extra in-memory copy of the national frame is a deliberate tradeoff so MVT
tile requests and repeated ``/districts`` calls with the same weights do not
re-score thousands of rows on every request (CPU + GC pressure on 512MB).
"""

from __future__ import annotations

import os
import threading
from typing import Any

import geopandas as gpd

from .profiling import RequestProfile
from models.scoring import score_thi

_lock = threading.Lock()
_cached_key: tuple[Any, ...] | None = None
_cached_scored: gpd.GeoDataFrame | None = None


def get_scored_geo_dataframe(
    base: gpd.GeoDataFrame,
    weights: dict[str, float],
    active_keys: list[str],
    profile: RequestProfile | None = None,
) -> gpd.GeoDataFrame:
    if os.getenv("HILTI_DISABLE_SCORING_CACHE", "").strip() in {"1", "true", "yes"}:
        if profile is not None:
            profile.cache("scoring_cache", "disabled")
            with profile.stage("scoring", rows_before=len(base)) as stage:
                scored = score_thi(base, weights, active_keys)
                stage.set_rows_after(len(scored))
        else:
            scored = score_thi(base, weights, active_keys)
        return scored
    global _cached_key, _cached_scored
    key: tuple[Any, ...] = (tuple(sorted(weights.items())), tuple(active_keys))
    with _lock:
        if key == _cached_key and _cached_scored is not None:
            if profile is not None:
                profile.cache("scoring_cache", "hit", rows=len(_cached_scored))
                profile.add_stage("scoring", rows_before=len(base), rows_after=len(_cached_scored), meta={"cache": "hit"})
            return _cached_scored
        if profile is not None:
            profile.cache("scoring_cache", "miss")
            with profile.stage("scoring", rows_before=len(base)) as stage:
                scored = score_thi(base, weights, active_keys)
                stage.set_rows_after(len(scored))
        else:
            scored = score_thi(base, weights, active_keys)
        _cached_key = key
        _cached_scored = scored
        return _cached_scored
