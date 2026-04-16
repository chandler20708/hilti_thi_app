"""Dynamic Mapbox Vector Tiles (MVT) for district polygons in Web Mercator."""

from __future__ import annotations

import math
from typing import Annotated, Any

import geopandas as gpd
import mercantile
import pandas as pd
from fastapi import APIRouter, Query, Response
from mapbox_vector_tile import encode
from mapbox_vector_tile.encoder import on_invalid_geometry_ignore
from starlette.concurrency import run_in_threadpool

from controllers.filters import apply_filters
from models.district_data import GEOM_MAP_LOW, GEOM_MAP_MID, build_api_map_frame
from models.scoring import DEFAULT_WEIGHTS, factor_catalog

from .profiling import RequestProfile
from .scoring_cache import get_scored_geo_dataframe
from .spatial import clip_to_bounds

router = APIRouter(tags=["tiles"])

_tile_base: gpd.GeoDataFrame | None = None


def set_mvt_base(gdf: gpd.GeoDataFrame) -> None:
    global _tile_base
    _tile_base = gdf


def get_mvt_base() -> gpd.GeoDataFrame:
    if _tile_base is None:
        raise RuntimeError("MVT tile base GeoDataFrame was not initialised.")
    return _tile_base

_MVT_CACHE: dict[str, bytes] = {}
_MVT_CACHE_ORDER: list[str] = []
_MVT_MAX = 180


def _mvt_cache_get(key: str) -> bytes | None:
    return _MVT_CACHE.get(key)


def _mvt_cache_set(key: str, payload: bytes) -> None:
    if key in _MVT_CACHE:
        _MVT_CACHE_ORDER.remove(key)
    elif len(_MVT_CACHE_ORDER) >= _MVT_MAX:
        old = _MVT_CACHE_ORDER.pop(0)
        del _MVT_CACHE[old]
    _MVT_CACHE[key] = payload
    _MVT_CACHE_ORDER.append(key)


def _parse_weights(
    w_mps: float | None,
    w_cas: float | None,
    w_cps: float | None,
    w_gii: float | None,
    w_pis: float | None,
) -> dict[str, float]:
    weights = DEFAULT_WEIGHTS.copy()
    overrides = {"mps": w_mps, "cas": w_cas, "cps": w_cps, "gii": w_gii, "pis": w_pis}
    for key, value in overrides.items():
        if value is not None:
            weights[key] = max(0.0, float(value))
    return weights


def _parse_active_keys(active: str) -> list[str]:
    chosen = [item.strip() for item in active.split(",") if item.strip()]
    return chosen or [factor.key for factor in factor_catalog()]


def _geom_column_for_tile(z: int) -> str | None:
    if z <= 6:
        return GEOM_MAP_LOW
    if z <= 11:
        return GEOM_MAP_MID
    return None


def _mvt_properties(row: pd.Series) -> dict[str, Any]:
    props: dict[str, Any] = {}
    pid = row.get("post_dist", row.get("PostDist"))
    if pid is not None and pd.notna(pid):
        props["post_dist"] = str(pid)
    for key in (
        "market_opportunity_score",
        "retention_health",
        "thi_score",
        "competition_pressure",
        "primary_segment",
        "data_source",
    ):
        val = row.get(key)
        if val is None or (isinstance(val, float) and (math.isnan(val) or pd.isna(val))):
            continue
        if isinstance(val, (int, float, str, bool)):
            props[key] = val
    return props


@router.get("/tiles/{z}/{x}/{y}.mvt")
async def district_vector_tile(
    z: int,
    x: int,
    y: int,
    post_area: Annotated[str, Query()] = "All",
    sprawl: Annotated[str, Query()] = "All",
    district: Annotated[str, Query()] = "All",
    segment: Annotated[str, Query()] = "All",
    active: Annotated[str, Query()] = "",
    w_mps: Annotated[float | None, Query()] = None,
    w_cas: Annotated[float | None, Query()] = None,
    w_cps: Annotated[float | None, Query()] = None,
    w_gii: Annotated[float | None, Query()] = None,
    w_pis: Annotated[float | None, Query()] = None,
) -> Response:
    profile = RequestProfile(
        "/tiles",
        params={
            "z": z,
            "x": x,
            "y": y,
            "post_area": post_area,
            "sprawl": sprawl,
            "district": district,
            "segment": segment,
            "active": active,
        },
    )
    if z < 0 or z > 14 or x < 0 or y < 0:
        profile.set_summary(cache_hit=False, result_rows=0)
        profile.finish(response_bytes=0)
        return _tile_response(b"")

    tile = mercantile.Tile(x, y, z)
    west, south, east, north = mercantile.bounds(tile)
    xy = mercantile.xy_bounds(tile)
    quant = (xy.left, xy.bottom, xy.right, xy.top)

    with profile.stage("query_parse") as stage:
        weights = _parse_weights(w_mps, w_cas, w_cps, w_gii, w_pis)
        active_keys = _parse_active_keys(active)
        stage.update_meta(weights=weights, active_key_count=len(active_keys))
    cache_key = (
        f"{z}:{x}:{y}:{post_area}:{sprawl}:{district}:{segment}:{active}:"
        f"{weights['mps']:.4f}:{weights['cas']:.4f}:{weights['cps']:.4f}:{weights['gii']:.4f}:{weights['pis']:.4f}"
    )
    with profile.stage("mvt_cache_lookup") as stage:
        hit = _mvt_cache_get(cache_key)
        stage.update_meta(cache_key=cache_key)
    if hit is not None:
        profile.cache("mvt_cache", "hit", bytes=len(hit))
        profile.set_summary(cache_hit=True)
        profile.finish(response_bytes=len(hit))
        return _tile_response(hit)
    profile.cache("mvt_cache", "miss")

    body = await run_in_threadpool(
        _build_tile_body,
        z,
        west,
        south,
        east,
        north,
        quant,
        post_area,
        sprawl,
        district,
        segment,
        active_keys,
        weights,
        profile,
    )
    if len(body) < 900_000:
        _mvt_cache_set(cache_key, body)
    profile.set_summary(cache_hit=False)
    profile.finish(response_bytes=len(body))
    return _tile_response(body)


def _build_tile_body(
    z: int,
    west: float,
    south: float,
    east: float,
    north: float,
    quant: tuple[float, float, float, float],
    post_area: str,
    sprawl: str,
    district: str,
    segment: str,
    active_keys: list[str],
    weights: dict[str, float],
    profile: RequestProfile | None = None,
) -> bytes:
    profile = profile or RequestProfile("/tiles-build", enabled=False)
    base = get_mvt_base()
    scored = get_scored_geo_dataframe(base, weights, active_keys, profile=profile)
    with profile.stage("filtering", rows_before=len(scored)) as stage:
        filtered = apply_filters(
            scored,
            {"post_area": post_area, "sprawl": sprawl, "district": district, "segment": segment},
        )
        stage.set_rows_after(len(filtered))
    pad = 0.0012 * (14 - min(z, 14) + 1)
    viewport = clip_to_bounds(filtered, west, south, east, north, pad=pad, profile=profile)
    if viewport.empty:
        profile.set_summary(result_rows=0)
        with profile.stage("mvt_encode", rows_before=0, rows_after_default=0) as stage:
            empty_body = encode(
                [{"name": "districts", "features": []}],
                per_layer_options={"districts": {"quantize_bounds": quant, "on_invalid_geometry": on_invalid_geometry_ignore}},
            )
            stage.update_meta(empty=True)
        return empty_body

    col = _geom_column_for_tile(z)
    with profile.stage("geometry_prep", rows_before=len(viewport)) as stage:
        if col and col in viewport.columns:
            plot_gdf = gpd.GeoDataFrame(
                viewport.drop(columns=[GEOM_MAP_LOW, GEOM_MAP_MID], errors="ignore").copy(),
                geometry=viewport[col],
                crs=viewport.crs,
            )
            stage.update_meta(geometry_source=col)
        else:
            plot_gdf = build_api_map_frame(
                viewport,
                max(6, min(z, 12)),
                allow_centroid_fallback=False,
                profile=profile,
            )
            stage.update_meta(geometry_source="build_api_map_frame")
        stage.set_rows_after(len(plot_gdf))

    with profile.stage("crs_transform", rows_before=len(plot_gdf), rows_after_default=len(plot_gdf)) as stage:
        plot_3857 = plot_gdf.to_crs(3857)
        stage.update_meta(target_epsg=3857)
    feats: list[dict[str, object]] = []
    with profile.stage("feature_prep", rows_before=len(plot_3857)) as stage:
        for _, row in plot_3857.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            try:
                feats.append({"geometry": geom, "properties": _mvt_properties(row)})
            except Exception:
                continue
        stage.set_rows_after(len(feats))
    profile.set_summary(result_rows=len(feats))
    with profile.stage("mvt_encode", rows_before=len(feats), rows_after_default=len(feats)) as stage:
        body = encode(
            [{"name": "districts", "features": feats}],
            per_layer_options={
                "districts": {
                    "quantize_bounds": quant,
                    "on_invalid_geometry": on_invalid_geometry_ignore,
                    "check_winding_order": False,
                }
            },
        )
        stage.update_meta(quantize_bounds=quant)
    return body


def _tile_response(body: bytes) -> Response:
    return Response(
        content=body,
        media_type="application/vnd.mapbox-vector-tile",
        headers={
            "Cache-Control": "public, max-age=300, s-maxage=900, stale-while-revalidate=86400",
            "Vary": "Accept-Encoding, Origin",
            "X-Map-Backend": "districts-mvt",
        },
    )
