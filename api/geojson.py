from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import geopandas as gpd
import orjson
import pandas as pd


def geojson_bytes_from_frame(gdf: gpd.GeoDataFrame) -> bytes:
    properties_columns = [column for column in gdf.columns if column != "geometry"]
    features: list[dict[str, Any]] = []
    for row in gdf.itertuples(index=False):
        row_dict = row._asdict()
        geometry = row_dict.pop("geometry", None)
        if geometry is None or geometry.is_empty:
            continue
        properties = {key: _json_safe(value) for key, value in row_dict.items()}
        features.append(
            {
                "type": "Feature",
                "geometry": geometry.__geo_interface__,
                "properties": {key: properties[key] for key in properties_columns if key in properties},
            }
        )
    return orjson.dumps(
        {"type": "FeatureCollection", "features": features},
        option=orjson.OPT_SERIALIZE_NUMPY,
    )


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
