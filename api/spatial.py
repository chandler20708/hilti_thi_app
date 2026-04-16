from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box


def clip_to_bounds(
    gdf: gpd.GeoDataFrame,
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    *,
    pad: float = 0.0,
) -> gpd.GeoDataFrame:
    """Use the GeoPandas spatial index first, then a precise intersect filter."""
    if None in {west, south, east, north}:
        return gdf

    minx = float(west) - pad
    miny = float(south) - pad
    maxx = float(east) + pad
    maxy = float(north) + pad
    bounds = (minx, miny, maxx, maxy)

    try:
        hits = list(gdf.sindex.intersection(bounds))
    except Exception:
        hits = []

    if not hits:
        try:
            return gdf.cx[minx:maxx, miny:maxy].copy()
        except Exception:
            return gdf.iloc[0:0].copy()

    subset = gdf.iloc[hits]
    window = box(*bounds)
    try:
        return subset.loc[subset.intersects(window)].copy()
    except Exception:
        return subset.copy()
