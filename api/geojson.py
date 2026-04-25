from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import geopandas as gpd
import orjson
import pandas as pd
from pandas.api import types as pd_types
from shapely.geometry.base import BaseGeometry


def geojson_bytes_from_frame(gdf: gpd.GeoDataFrame) -> bytes:
    columns = list(gdf.columns)
    geometry_idx = columns.index("geometry")
    property_indices = [
        (idx, column, _converter_for_column(gdf[column]))
        for idx, column in enumerate(columns)
        if column != "geometry"
    ]
    features: list[dict[str, Any]] = []
    for row in gdf.itertuples(index=False, name=None):
        geometry = row[geometry_idx]
        if geometry is None or geometry.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": _geometry_to_geojson(geometry),
                "properties": {column: converter(row[idx]) for idx, column, converter in property_indices},
            }
        )
    return orjson.dumps(
        {"type": "FeatureCollection", "features": features},
        option=orjson.OPT_SERIALIZE_NUMPY,
    )


def _geometry_to_geojson(geometry: BaseGeometry) -> dict[str, Any]:
    if geometry.geom_type == "Point":
        return {"type": "Point", "coordinates": [round(geometry.x, 6), round(geometry.y, 6)]}
    return geometry.__geo_interface__


def _converter_for_column(series: pd.Series):
    dtype = series.dtype
    if pd_types.is_float_dtype(dtype):
        return _float_safe
    if pd_types.is_integer_dtype(dtype):
        return _item_safe
    if pd_types.is_bool_dtype(dtype):
        return _item_safe
    if pd_types.is_string_dtype(dtype) or pd_types.is_object_dtype(dtype) or isinstance(dtype, pd.CategoricalDtype):
        return _object_safe
    return _json_safe


def _float_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        return None if math.isnan(value) else value
    except TypeError:
        return None if pd.isna(value) else value


def _item_safe(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, "item"):
        try:
            item = value.item()
            if item is None or item is pd.NA or item is pd.NaT:
                return None
            if isinstance(item, float):
                return None if math.isnan(item) else item
            return item
        except Exception:
            return value
    return value


def _object_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (str, int, float, bool)):
        return value
    return _json_safe(value)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            item = value.item()
            if item is None:
                return None
            if isinstance(item, float):
                return None if math.isnan(item) else item
            if pd.isna(item):
                return None
            return item
        except Exception:
            return value
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str, dict)):
        return list(value)
    if pd.isna(value):
        return None
    return value
