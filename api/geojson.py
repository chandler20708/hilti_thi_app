from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import geopandas as gpd
import orjson
import pandas as pd
from shapely.geometry.base import BaseGeometry


def geojson_bytes_from_frame(gdf: gpd.GeoDataFrame) -> bytes:
    columns = list(gdf.columns)
    geometry_idx = columns.index("geometry")
    property_indices = [(idx, column) for idx, column in enumerate(columns) if column != "geometry"]
    features: list[dict[str, Any]] = []
    for row in gdf.itertuples(index=False, name=None):
        geometry = row[geometry_idx]
        if geometry is None or geometry.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": _geometry_to_geojson(geometry),
                "properties": {column: _json_safe(row[idx]) for idx, column in property_indices},
            }
        )
    return orjson.dumps(
        {"type": "FeatureCollection", "features": features},
        option=orjson.OPT_SERIALIZE_NUMPY,
    )


def _geometry_to_geojson(geometry: BaseGeometry) -> dict[str, Any]:
    if geometry.geom_type == "Point":
        return {"type": "Point", "coordinates": [geometry.x, geometry.y]}
    return geometry.__geo_interface__


def _json_safe(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str, dict)):
        return list(value)
    return value
