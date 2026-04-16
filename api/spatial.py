from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from .profiling import RequestProfile


def clip_to_bounds(
    gdf: gpd.GeoDataFrame,
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    *,
    pad: float = 0.0,
    precise: bool = True,
    profile: RequestProfile | None = None,
) -> gpd.GeoDataFrame:
    """Use the GeoPandas spatial index first, then a precise intersect filter."""
    if None in {west, south, east, north}:
        return gdf

    minx = float(west) - pad
    miny = float(south) - pad
    maxx = float(east) + pad
    maxy = float(north) + pad
    bounds = (minx, miny, maxx, maxy)

    if profile is not None:
        with profile.stage("bbox_clip_sindex", rows_before=len(gdf)) as stage:
            try:
                hits = list(gdf.sindex.intersection(bounds))
            except Exception as exc:
                hits = []
                stage.update_meta(error=type(exc).__name__)
            stage.set_rows_after(len(hits))
    else:
        try:
            hits = list(gdf.sindex.intersection(bounds))
        except Exception:
            hits = []

    if not hits:
        if profile is not None:
            with profile.stage("bbox_clip_fallback", rows_before=len(gdf)) as stage:
                try:
                    fallback = gdf.cx[minx:maxx, miny:maxy]
                except Exception as exc:
                    fallback = gdf.iloc[0:0]
                    stage.update_meta(error=type(exc).__name__)
                stage.set_rows_after(len(fallback))
            profile.add_stage(
                "precise_intersects",
                rows_before=len(fallback),
                rows_after=len(fallback),
                meta={"skipped": True, "reason": "no_sindex_hits"},
            )
            return fallback
        try:
            return gdf.cx[minx:maxx, miny:maxy]
        except Exception:
            return gdf.iloc[0:0]

    if profile is not None:
        with profile.stage("bbox_clip_subset", rows_before=len(gdf)) as stage:
            subset = gdf.iloc[hits]
            stage.set_rows_after(len(subset))
    else:
        subset = gdf.iloc[hits]
    if not precise:
        if profile is not None:
            profile.add_stage(
                "precise_intersects",
                rows_before=len(subset),
                rows_after=len(subset),
                meta={"skipped": True, "reason": "precision_disabled"},
            )
        return subset
    window = box(*bounds)
    if profile is not None:
        with profile.stage("precise_intersects", rows_before=len(subset)) as stage:
            try:
                precise_subset = subset.loc[subset.intersects(window)]
            except Exception as exc:
                precise_subset = subset
                stage.update_meta(error=type(exc).__name__)
            stage.set_rows_after(len(precise_subset))
        return precise_subset
    try:
        return subset.loc[subset.intersects(window)]
    except Exception:
        return subset
