from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

import geopandas as gpd

from controllers.filters import build_filter_mask
from .profiling import RequestProfile

_LOCK = threading.Lock()
_CACHE: OrderedDict[tuple[Any, ...], gpd.GeoDataFrame] = OrderedDict()
_MAX_ENTRIES = 8


def get_filtered_geo_dataframe(
    scored: gpd.GeoDataFrame,
    filters: dict[str, object],
    weights: dict[str, float],
    active_keys: list[str],
    profile: RequestProfile | None = None,
) -> gpd.GeoDataFrame:
    key = (
        tuple(sorted(filters.items())),
        tuple(sorted(weights.items())),
        tuple(active_keys),
    )
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            if profile is not None:
                profile.cache("filtered_frame_cache", "hit", rows=len(hit))
                profile.add_stage("filtering", rows_before=len(scored), rows_after=len(hit), meta={"cache": "hit"})
            return hit

    if profile is not None:
        profile.cache("filtered_frame_cache", "miss")
        with profile.stage("filtering", rows_before=len(scored)) as stage:
            mask = build_filter_mask(scored, filters)
            filtered = scored if bool(mask.all()) else scored.loc[mask]
            stage.set_rows_after(len(filtered))
    else:
        mask = build_filter_mask(scored, filters)
        filtered = scored if bool(mask.all()) else scored.loc[mask]

    with _LOCK:
        _CACHE[key] = filtered
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)
    return filtered
