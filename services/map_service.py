from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from typing import Any

import geopandas as gpd
from aiohttp import web

from config import MAP_HOST, MAP_PORT
from controllers.filters import apply_filters
from models.scoring import DEFAULT_WEIGHTS, factor_catalog, score_thi


_SERVICE_STATE: dict[str, Any] = {
    "thread": None,
    "base_url": f"http://{MAP_HOST}:{MAP_PORT}",
    "gdf": None,
    "port": MAP_PORT,
}


def ensure_map_service(gdf: gpd.GeoDataFrame) -> str:
    _SERVICE_STATE["gdf"] = gdf
    thread = _SERVICE_STATE.get("thread")
    if thread and thread.is_alive():
        return _SERVICE_STATE["base_url"]

    chosen_port = _find_free_port(MAP_HOST, int(_SERVICE_STATE.get("port", MAP_PORT)))
    _SERVICE_STATE["port"] = chosen_port
    _SERVICE_STATE["base_url"] = f"http://{MAP_HOST}:{chosen_port}"

    thread = threading.Thread(target=_run_server, name="hilti-map-service", daemon=True)
    thread.start()
    _SERVICE_STATE["thread"] = thread
    time.sleep(0.6)
    return _SERVICE_STATE["base_url"]


def _run_server() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = web.Application()
    app.router.add_get("/health", _health)
    app.router.add_get("/districts", _districts)

    runner = web.AppRunner(app)

    async def starter() -> None:
        await runner.setup()
        site = web.TCPSite(runner, MAP_HOST, int(_SERVICE_STATE["port"]))
        await site.start()

    loop.run_until_complete(starter())
    loop.run_forever()


def _find_free_port(host: str, start_port: int) -> int:
    for port in range(start_port, start_port + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError("Unable to find a free local port for the map service.")


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"}, headers={"Access-Control-Allow-Origin": "*"})


async def _districts(request: web.Request) -> web.Response:
    gdf: gpd.GeoDataFrame | None = _SERVICE_STATE.get("gdf")
    if gdf is None:
        return web.json_response({"error": "Dataset unavailable"}, status=503, headers={"Access-Control-Allow-Origin": "*"})

    active = _parse_active_keys(request)
    scored = score_thi(gdf, _parse_weights(request), active)
    filtered = apply_filters(
        scored,
        {
            "post_area": request.query.get("post_area", "All"),
            "sprawl": request.query.get("sprawl", "All"),
            "district": request.query.get("district", "All"),
            "segment": request.query.get("segment", "All"),
            "observed_only": request.query.get("observed_only", "0") == "1",
        },
    )
    viewport = _apply_bbox(filtered, request)
    simplified = _simplify(viewport, int(float(request.query.get("zoom", "6"))))

    payload = json.loads(_export_geojson(simplified))
    return web.Response(
        text=json.dumps(payload),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


def _parse_active_keys(request: web.Request) -> list[str]:
    raw = request.query.get("active", "")
    chosen = [item.strip() for item in raw.split(",") if item.strip()]
    return chosen or [factor.key for factor in factor_catalog()]


def _parse_weights(request: web.Request) -> dict[str, float]:
    weights = DEFAULT_WEIGHTS.copy()
    for key in list(weights):
        raw = request.query.get(f"w_{key}")
        if raw is None:
            continue
        try:
            weights[key] = max(0.0, float(raw))
        except ValueError:
            continue
    return weights


def _apply_bbox(gdf: gpd.GeoDataFrame, request: web.Request) -> gpd.GeoDataFrame:
    required = ["west", "south", "east", "north"]
    if not all(key in request.query for key in required):
        return gdf

    west = float(request.query["west"])
    south = float(request.query["south"])
    east = float(request.query["east"])
    north = float(request.query["north"])
    pad = _padding_for_zoom(int(float(request.query.get("zoom", "6"))))
    return gdf.cx[west - pad : east + pad, south - pad : north + pad]


def _padding_for_zoom(zoom: int) -> float:
    if zoom <= 5:
        return 0.8
    if zoom <= 7:
        return 0.35
    if zoom <= 9:
        return 0.18
    return 0.08


def _simplification_tolerance(zoom: int) -> float:
    if zoom <= 5:
        return 0.05
    if zoom == 6:
        return 0.02
    if zoom == 7:
        return 0.008
    if zoom == 8:
        return 0.003
    if zoom == 9:
        return 0.0015
    return 0.0005


def _simplify(gdf: gpd.GeoDataFrame, zoom: int) -> gpd.GeoDataFrame:
    simplified = gdf.copy()
    simplified["geometry"] = simplified.geometry.simplify(_simplification_tolerance(zoom), preserve_topology=True)
    return simplified


def _export_geojson(gdf: gpd.GeoDataFrame) -> str:
    export_columns = [
        "PostDist",
        "PostArea",
        "Sprawl",
        "primary_segment",
        "observed_flag",
        "data_source",
        "center_lat",
        "center_lon",
        "market_opportunity_score",
        "acquisition_opportunity",
        "retention_risk",
        "competition_pressure",
        "mps",
        "cas",
        "cps",
        "gii",
        "pis",
        "territory_count_demo",
        "area_sq_mi_demo",
        "ratio_demo",
        "existing_accounts",
        "lead_volume",
        "thi_score",
        "geometry",
    ]
    safe = gdf[export_columns].copy().rename(
        columns={
            "PostDist": "post_dist",
            "PostArea": "post_area",
            "Sprawl": "sprawl",
            "primary_segment": "primary_segment",
            "observed_flag": "observed_flag",
            "data_source": "data_source",
            "center_lat": "center_lat",
            "center_lon": "center_lon",
            "market_opportunity_score": "market_opportunity_score",
            "acquisition_opportunity": "acquisition_opportunity",
            "retention_risk": "retention_risk",
            "competition_pressure": "competition_pressure",
            "territory_count_demo": "territory_count_demo",
            "area_sq_mi_demo": "area_sq_mi_demo",
            "ratio_demo": "ratio_demo",
            "existing_accounts": "existing_accounts",
            "lead_volume": "lead_volume",
            "thi_score": "thi_score",
        }
    )
    numeric_columns = [col for col in safe.columns if col != "geometry"]
    for column in numeric_columns:
        if str(safe[column].dtype).startswith(("float", "int")):
            safe[column] = safe[column].round(2)
    return safe.to_json()
