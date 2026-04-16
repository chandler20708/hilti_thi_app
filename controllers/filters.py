from __future__ import annotations

import geopandas as gpd
import pandas as pd


def build_filter_mask(gdf: gpd.GeoDataFrame, filters: dict[str, object]) -> pd.Series:
    mask = pd.Series(True, index=gdf.index)
    if filters.get("post_area") and filters["post_area"] != "All" and "PostArea" in gdf.columns:
        mask &= gdf["PostArea"] == filters["post_area"]
    if filters.get("sprawl") and filters["sprawl"] != "All":
        mask &= gdf["Sprawl"] == filters["sprawl"]
    if filters.get("district") and filters["district"] != "All":
        mask &= gdf["PostDist"] == filters["district"]
    if filters.get("segment") and filters["segment"] != "All":
        mask &= gdf["primary_segment"] == filters["segment"]
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
