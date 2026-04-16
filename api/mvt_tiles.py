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

from controllers.filters import apply_filters
from models.district_data import GEOM_MAP_LOW, GEOM_MAP_MID, build_api_map_frame
from models.scoring import DEFAULT_WEIGHTS, factor_catalog

from .scoring_cache import get_scored_geo_dataframe

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
    if z <= 10:
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
def district_vector_tile(
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
    if z < 0 or z > 14 or x < 0 or y < 0:
        return Response(content=b"", media_type="application/vnd.mapbox-vector-tile")

    tile = mercantile.Tile(x, y, z)
    west, south, east, north = mercantile.bounds(tile)
    xy = mercantile.xy_bounds(tile)
    quant = (xy.left, xy.bottom, xy.right, xy.top)

    weights = _parse_weights(w_mps, w_cas, w_cps, w_gii, w_pis)
    cache_key = (
        f"{z}:{x}:{y}:{sprawl}:{district}:{segment}:{active}:"
        f"{weights['mps']:.4f}:{weights['cas']:.4f}:{weights['cps']:.4f}:{weights['gii']:.4f}:{weights['pis']:.4f}"
    )
    hit = _mvt_cache_get(cache_key)
    if hit is not None:
        return Response(content=hit, media_type="application/vnd.mapbox-vector-tile")

    base = get_mvt_base()
    active_keys = _parse_active_keys(active)
    scored = get_scored_geo_dataframe(base, weights, active_keys)
    filtered = apply_filters(
        scored,
        {"post_area": post_area, "sprawl": sprawl, "district": district, "segment": segment},
    )
    pad = 0.0012 * (14 - min(z, 14) + 1)
    viewport = filtered.cx[west - pad : east + pad, south - pad : north + pad]
    if viewport.empty:
        body = encode(
            [{"name": "districts", "features": []}],
            per_layer_options={"districts": {"quantize_bounds": quant, "on_invalid_geometry": on_invalid_geometry_ignore}},
        )
        _mvt_cache_set(cache_key, body)
        return Response(content=body, media_type="application/vnd.mapbox-vector-tile")

    col = _geom_column_for_tile(z)
    if col and col in viewport.columns:
        plot_gdf = viewport.set_geometry(col, crs=viewport.crs)
    else:
        plot_gdf = build_api_map_frame(
            viewport,
            max(6, min(z, 12)),
            allow_centroid_fallback=False,
        )

    plot_3857 = plot_gdf.to_crs(3857)
    feats: list[dict[str, object]] = []
    for _, row in plot_3857.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            feats.append({"geometry": geom, "properties": _mvt_properties(row)})
        except Exception:
            continue

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
    if len(body) < 900_000:
        _mvt_cache_set(cache_key, body)
    return Response(content=body, media_type="application/vnd.mapbox-vector-tile")
