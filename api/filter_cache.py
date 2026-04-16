from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

import geopandas as gpd

from controllers.filters import build_filter_mask

_LOCK = threading.Lock()
_CACHE: OrderedDict[tuple[Any, ...], gpd.GeoDataFrame] = OrderedDict()
_MAX_ENTRIES = 8


def get_filtered_geo_dataframe(
    scored: gpd.GeoDataFrame,
    filters: dict[str, object],
    weights: dict[str, float],
    active_keys: list[str],
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
            return hit

    mask = build_filter_mask(scored, filters)
    filtered = scored if bool(mask.all()) else scored.loc[mask]

    with _LOCK:
        _CACHE[key] = filtered
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)
    return filtered
