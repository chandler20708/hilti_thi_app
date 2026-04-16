from __future__ import annotations

import geopandas as gpd


def apply_filters(gdf: gpd.GeoDataFrame, filters: dict[str, object]) -> gpd.GeoDataFrame:
    """Narrow the frame; returns the same object when no filters apply (saves a full copy)."""
    out: gpd.GeoDataFrame = gdf
    if filters.get("sprawl") and filters["sprawl"] != "All":
        out = out.loc[out["Sprawl"] == filters["sprawl"]]
    if filters.get("district") and filters["district"] != "All":
        out = out.loc[out["PostDist"] == filters["district"]]
    if filters.get("segment") and filters["segment"] != "All":
        out = out.loc[out["primary_segment"] == filters["segment"]]
    if out is gdf:
        return gdf
    return out.copy()


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
