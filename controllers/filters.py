from __future__ import annotations

import geopandas as gpd
import pandas as pd

from models.district_data import SEGMENT_MODE_COLUMNS, resolve_segment_mode


def build_filter_mask(gdf: gpd.GeoDataFrame, filters: dict[str, object]) -> pd.Series:
    mask = pd.Series(True, index=gdf.index)
    if filters.get("post_area") and filters["post_area"] != "All" and "PostArea" in gdf.columns:
        mask &= gdf["PostArea"] == filters["post_area"]
    if filters.get("sprawl") and filters["sprawl"] != "All":
        mask &= gdf["Sprawl"] == filters["sprawl"]
    if filters.get("district") and filters["district"] != "All":
        mask &= gdf["PostDist"] == filters["district"]
    segment_mode = resolve_segment_mode(str(filters.get("segment_mode", "primary_segment")))
    segment_column = SEGMENT_MODE_COLUMNS.get(segment_mode, "primary_segment")
    if filters.get("segment") and filters["segment"] != "All" and segment_column in gdf.columns:
        mask &= gdf[segment_column] == filters["segment"]
    return mask


def apply_filters(gdf: gpd.GeoDataFrame, filters: dict[str, object]) -> gpd.GeoDataFrame:
    """Narrow the frame; returns the same object when no filters apply (saves a full copy)."""
    mask = build_filter_mask(gdf, filters)
    if bool(mask.all()):
        return gdf
    return gdf.loc[mask].copy()


def get_focus_record(gdf: gpd.GeoDataFrame, filters: dict[str, object]) -> dict[str, object] | None:
    district = filters.get("district")
    sprawl = filters.get("sprawl")

    # Only geographic filters should drive viewport changes.
    if district and district != "All":
        subset = gdf.loc[gdf["PostDist"] == district]
        label = f"Territory: {district}"
    elif sprawl and sprawl != "All":
        subset = gdf.loc[gdf["Sprawl"] == sprawl]
        label = f"City: {sprawl}"
    else:
        return None

    if subset.empty:
        return None

    minx, miny, maxx, maxy = subset.total_bounds
    center = subset.geometry.union_all().representative_point()

    return {
        "label": label,
        "center_lat": float(center.y),
        "center_lon": float(center.x),
        "bounds": [[float(miny), float(minx)], [float(maxy), float(maxx)]],
    }
