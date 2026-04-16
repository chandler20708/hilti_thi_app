from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

import geopandas as gpd
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.gzip import GZipMiddleware

from .query_cache import BytesTTLCache
from config import API_CORS_ORIGINS
from controllers.filters import apply_filters
from models.district_data import build_api_map_frame, load_prototype_geo_dataframe
from models.scoring import DEFAULT_WEIGHTS, factor_catalog

from .mvt_tiles import router as mvt_router, set_mvt_base
from .scoring_cache import get_scored_geo_dataframe

app = FastAPI(title="Hilti Territory Map API")

# Tight defaults for 512MB hosts: fewer/lighter cached bodies than before.
_DISTRICTS_CACHE = BytesTTLCache(max_entries=10, ttl_seconds=45.0, max_entry_bytes=1_400_000)


def _allowed_origins() -> list[str]:
    if API_CORS_ORIGINS.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in API_CORS_ORIGINS.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=800)

app.include_router(mvt_router)


@app.on_event("startup")
def _load_base_dataframe() -> None:
    app.state.base_gdf = load_prototype_geo_dataframe()
    set_mvt_base(app.state.base_gdf)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _districts_cache_key(request: Request) -> str:
    pairs = sorted(request.query_params.multi_items())
    return urlencode(pairs)


@app.get("/districts")
def districts(
    request: Request,
    west: Annotated[float | None, Query()] = None,
    south: Annotated[float | None, Query()] = None,
    east: Annotated[float | None, Query()] = None,
    north: Annotated[float | None, Query()] = None,
    zoom: Annotated[int, Query(ge=1, le=18)] = 6,
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
    cache_key = _districts_cache_key(request)
    cached = _DISTRICTS_CACHE.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")

    gdf: gpd.GeoDataFrame = app.state.base_gdf
    weights = _parse_weights(w_mps, w_cas, w_cps, w_gii, w_pis)
    active_keys = _parse_active_keys(active)
    scored = get_scored_geo_dataframe(gdf, weights, active_keys)
    filtered = apply_filters(
        scored,
        {
            "post_area": post_area,
            "sprawl": sprawl,
            "district": district,
            "segment": segment,
        },
    )
    viewport = _apply_bbox(filtered, west, south, east, north, zoom)
    body = build_api_map_frame(viewport, zoom).to_json().encode("utf-8")
    _DISTRICTS_CACHE.set(cache_key, body)
    return Response(content=body, media_type="application/json")


def _parse_active_keys(active: str) -> list[str]:
    chosen = [item.strip() for item in active.split(",") if item.strip()]
    return chosen or [factor.key for factor in factor_catalog()]


def _parse_weights(
    w_mps: float | None,
    w_cas: float | None,
    w_cps: float | None,
    w_gii: float | None,
    w_pis: float | None,
) -> dict[str, float]:
    weights = DEFAULT_WEIGHTS.copy()
    overrides = {
        "mps": w_mps,
        "cas": w_cas,
        "cps": w_cps,
        "gii": w_gii,
        "pis": w_pis,
    }
    for key, value in overrides.items():
        if value is not None:
            weights[key] = max(0.0, float(value))
    return weights


def _apply_bbox(
    gdf: gpd.GeoDataFrame,
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    zoom: int,
) -> gpd.GeoDataFrame:
    if None in {west, south, east, north}:
        return gdf
    pad = _padding_for_zoom(zoom)
    return gdf.cx[west - pad : east + pad, south - pad : north + pad]


def _padding_for_zoom(zoom: int) -> float:
    if zoom <= 5:
        return 0.8
    if zoom <= 7:
        return 0.35
    if zoom <= 9:
        return 0.18
    return 0.08
