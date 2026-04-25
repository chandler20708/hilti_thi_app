from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

import geopandas as gpd
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from .filter_cache import get_filtered_geo_dataframe
from .geojson import geojson_bytes_from_frame
from .profiling import RequestProfile
from .query_cache import BytesTTLCache
from config import API_CORS_ORIGINS, env_float, env_int
from models.district_data import build_api_map_frame, load_prototype_geo_dataframe
from models.scoring import DEFAULT_WEIGHTS, factor_catalog

from .mvt_tiles import router as mvt_router, set_mvt_base
from .scoring_cache import get_scored_geo_dataframe
from .spatial import clip_to_bounds

app = FastAPI(title="Hilti Territory Map API")

# Tight defaults for 512MB hosts: keep the response cache bounded and biased
# toward smaller, recently reused viewport payloads rather than many large bodies.
_DISTRICTS_CACHE = BytesTTLCache(
    max_entries=env_int("HILTI_DISTRICTS_CACHE_MAX_ENTRIES", 18),
    ttl_seconds=env_float("HILTI_DISTRICTS_CACHE_TTL_SECONDS", 90.0),
    max_entry_bytes=env_int("HILTI_DISTRICTS_CACHE_MAX_ENTRY_BYTES", 1_500_000),
)
_PREWARM_DEFAULT_MAP = env_int("HILTI_PREWARM_DEFAULT_MAP", 1) != 0
_DEFAULT_MAP_BOUNDS = (-8.2, 49.8, 2.2, 60.9)
_DEFAULT_MAP_ZOOM = env_int("HILTI_DEFAULT_MAP_PREWARM_ZOOM", 5)
_PREWARMED_DISTRICTS: dict[str, bytes] = {}


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
    _ = app.state.base_gdf.sindex
    set_mvt_base(app.state.base_gdf)
    if _PREWARM_DEFAULT_MAP:
        _prewarm_default_districts(app.state.base_gdf)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _districts_cache_key(request: Request) -> str:
    metric_key = request.query_params.get("metric_key", "thi_score")
    pairs = [
        (key, value)
        for key, value in request.query_params.multi_items()
        if metric_key == "thi_score" or (key != "active" and not key.startswith("w_"))
    ]
    return _districts_cache_key_from_pairs(pairs)


def _districts_cache_key_from_pairs(pairs: list[tuple[str, object]]) -> str:
    return urlencode(sorted((key, str(value)) for key, value in pairs))


def _default_districts_query_pairs() -> list[tuple[str, object]]:
    active_keys = [factor.key for factor in factor_catalog()]
    pairs: list[tuple[str, object]] = [
        ("west", f"{_DEFAULT_MAP_BOUNDS[0]:.6f}"),
        ("south", f"{_DEFAULT_MAP_BOUNDS[1]:.6f}"),
        ("east", f"{_DEFAULT_MAP_BOUNDS[2]:.6f}"),
        ("north", f"{_DEFAULT_MAP_BOUNDS[3]:.6f}"),
        ("zoom", str(_DEFAULT_MAP_ZOOM)),
        ("metric_key", "thi_score"),
        ("active", ",".join(active_keys)),
    ]
    pairs.extend((f"w_{key}", str(DEFAULT_WEIGHTS[key])) for key in active_keys)
    return pairs


def _prewarm_default_districts(gdf: gpd.GeoDataFrame) -> None:
    cache_key = _districts_cache_key_from_pairs(_default_districts_query_pairs())
    if cache_key in _PREWARMED_DISTRICTS:
        return
    west, south, east, north = _DEFAULT_MAP_BOUNDS
    active = ",".join(factor.key for factor in factor_catalog())
    body = _build_districts_body(
        gdf,
        west,
        south,
        east,
        north,
        _DEFAULT_MAP_ZOOM,
        "All",
        "All",
        "All",
        "All",
        "primary_segment",
        "thi_score",
        active,
        DEFAULT_WEIGHTS["mps"],
        DEFAULT_WEIGHTS["cas"],
        DEFAULT_WEIGHTS["cps"],
        DEFAULT_WEIGHTS["gii"],
        DEFAULT_WEIGHTS["pis"],
        RequestProfile("/districts-prewarm", enabled=False),
    )
    _PREWARMED_DISTRICTS[cache_key] = body
    _DISTRICTS_CACHE.set(cache_key, body)
    app.state.default_districts_cache_key = cache_key
    app.state.default_districts_response_bytes = len(body)


@app.get("/districts")
async def districts(
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
    segment_mode: Annotated[str, Query()] = "primary_segment",
    metric_key: Annotated[str, Query()] = "thi_score",
    active: Annotated[str, Query()] = "",
    w_mps: Annotated[float | None, Query()] = None,
    w_cas: Annotated[float | None, Query()] = None,
    w_cps: Annotated[float | None, Query()] = None,
    w_gii: Annotated[float | None, Query()] = None,
    w_pis: Annotated[float | None, Query()] = None,
) -> Response:
    profile = RequestProfile(
        "/districts",
        params={
            "zoom": zoom,
            "has_bbox": None not in {west, south, east, north},
            "post_area": post_area,
            "sprawl": sprawl,
            "district": district,
            "segment": segment,
            "segment_mode": segment_mode,
            "metric_key": metric_key,
            "active": active,
        },
    )
    cache_key = _districts_cache_key(request)
    with profile.stage("districts_cache_lookup") as stage:
        cached = _DISTRICTS_CACHE.get(cache_key)
        stage.update_meta(cache_key=cache_key)
    if cached is not None:
        profile.cache("districts_cache", "hit", bytes=len(cached))
        profile.set_summary(cache_hit=True)
        profile.finish(response_bytes=len(cached))
        return _districts_response(cached)
    prewarmed = _PREWARMED_DISTRICTS.get(cache_key)
    if prewarmed is not None:
        _DISTRICTS_CACHE.set(cache_key, prewarmed)
        profile.cache("districts_cache", "hit", bytes=len(prewarmed), source="prewarmed_default")
        profile.set_summary(cache_hit=True, prewarmed_default=True)
        profile.finish(response_bytes=len(prewarmed))
        return _districts_response(prewarmed)
    profile.cache("districts_cache", "miss")

    gdf: gpd.GeoDataFrame = app.state.base_gdf
    body = await run_in_threadpool(
        _build_districts_body,
        gdf,
        west,
        south,
        east,
        north,
        zoom,
        post_area,
        sprawl,
        district,
        segment,
        segment_mode,
        metric_key,
        active,
        w_mps,
        w_cas,
        w_cps,
        w_gii,
        w_pis,
        profile,
    )
    _DISTRICTS_CACHE.set(cache_key, body)
    profile.set_summary(cache_hit=False, result_rows=None)
    profile.finish(response_bytes=len(body))
    return _districts_response(body)


def _build_districts_body(
    gdf: gpd.GeoDataFrame,
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    zoom: int,
    post_area: str,
    sprawl: str,
    district: str,
    segment: str,
    segment_mode: str,
    metric_key: str,
    active: str,
    w_mps: float | None,
    w_cas: float | None,
    w_cps: float | None,
    w_gii: float | None,
    w_pis: float | None,
    profile: RequestProfile | None = None,
) -> bytes:
    profile = profile or RequestProfile("/districts-build", enabled=False)
    with profile.stage("query_parse", rows_before=len(gdf), rows_after_default=len(gdf)) as stage:
        weights = _parse_weights(w_mps, w_cas, w_cps, w_gii, w_pis)
        active_keys = _parse_active_keys(active)
        needs_thi = metric_key == "thi_score"
        stage.update_meta(active_key_count=len(active_keys), weights=weights, metric_key=metric_key, needs_thi=needs_thi)
    if needs_thi:
        scored = get_scored_geo_dataframe(gdf, weights, active_keys, profile=profile)
    else:
        scored = gdf
        profile.cache("scoring_cache", "skipped")
        profile.add_stage(
            "scoring",
            rows_before=len(gdf),
            rows_after=len(gdf),
            meta={"skipped": True, "reason": "metric_does_not_need_thi", "metric_key": metric_key},
        )
    filters = {
        "post_area": post_area,
        "sprawl": sprawl,
        "district": district,
        "segment": segment,
        "segment_mode": segment_mode,
        "_needs_thi": needs_thi,
    }
    filter_weights = weights if needs_thi else DEFAULT_WEIGHTS
    filter_active_keys = active_keys if needs_thi else [factor.key for factor in factor_catalog()]
    filtered = get_filtered_geo_dataframe(scored, filters, filter_weights, filter_active_keys, profile=profile)
    viewport = _apply_bbox(filtered, west, south, east, north, zoom, profile=profile)
    map_frame = build_api_map_frame(viewport, zoom, profile=profile)
    profile.set_summary(result_rows=len(map_frame))
    with profile.stage("serialization", rows_before=len(map_frame), rows_after_default=len(map_frame)) as stage:
        body = geojson_bytes_from_frame(map_frame)
        stage.update_meta(format="geojson")
    return body


def _districts_response(body: bytes) -> Response:
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=30, s-maxage=120, stale-while-revalidate=300",
            "Vary": "Accept-Encoding, Origin",
            "X-Map-Backend": "districts-json",
        },
    )


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
    profile: RequestProfile | None = None,
) -> gpd.GeoDataFrame:
    if None in {west, south, east, north}:
        return gdf
    pad = _padding_for_zoom(zoom)
    return clip_to_bounds(gdf, west, south, east, north, pad=pad, precise=zoom >= 7, profile=profile)


def _padding_for_zoom(zoom: int) -> float:
    if zoom <= 5:
        return 0.8
    if zoom <= 7:
        return 0.35
    if zoom <= 9:
        return 0.18
    return 0.08
