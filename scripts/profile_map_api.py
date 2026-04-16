from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("HILTI_PROFILE_MAP_API", "1")

import mercantile  # noqa: E402
from api.main import _load_base_dataframe, app, districts  # noqa: E402
from api.mvt_tiles import district_vector_tile  # noqa: E402


@dataclass
class Case:
    label: str
    path: str
    params: dict[str, Any]
    warm_repeats: int = 0


class ProfileCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.append(json.loads(record.getMessage()))
        except Exception:
            return


def _pad_bounds(bounds: tuple[float, float, float, float], factor: float) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    dx = (maxx - minx) * factor
    dy = (maxy - miny) * factor
    return (minx - dx, miny - dy, maxx + dx, maxy + dy)


def _bbox_params(bounds: tuple[float, float, float, float], zoom: int) -> dict[str, Any]:
    west, south, east, north = bounds
    return {
        "west": round(west, 6),
        "south": round(south, 6),
        "east": round(east, 6),
        "north": round(north, 6),
        "zoom": zoom,
    }


def _choose_cases() -> list[Case]:
    gdf = app.state.base_gdf
    national_bounds = _pad_bounds(tuple(gdf.total_bounds), 0.02)

    city_counts = (
        gdf.loc[gdf["Sprawl"].notna() & (gdf["Sprawl"] != "All")]
        .groupby("Sprawl")
        .size()
        .sort_values(ascending=False)
    )
    city_name = str(city_counts.index[0])
    city_gdf = gdf.loc[gdf["Sprawl"] == city_name]
    city_bounds = _pad_bounds(tuple(city_gdf.total_bounds), 0.12)

    local_row = city_gdf.sort_values("lead_volume", ascending=False).iloc[0]
    district_name = str(local_row["PostDist"])
    district_gdf = gdf.loc[gdf["PostDist"] == district_name]
    local_bounds = _pad_bounds(tuple(district_gdf.total_bounds), 0.25)

    center_x = float((city_bounds[0] + city_bounds[2]) / 2.0)
    center_y = float((city_bounds[1] + city_bounds[3]) / 2.0)
    tile = mercantile.tile(center_x, center_y, 11)

    return [
        Case(
            label="districts_national_low_zoom",
            path="/districts",
            params=_bbox_params(national_bounds, zoom=5),
            warm_repeats=1,
        ),
        Case(
            label="districts_medium_city",
            path="/districts",
            params={**_bbox_params(city_bounds, zoom=9), "sprawl": city_name},
            warm_repeats=1,
        ),
        Case(
            label="districts_narrow_local",
            path="/districts",
            params={**_bbox_params(local_bounds, zoom=12), "district": district_name, "sprawl": city_name},
            warm_repeats=1,
        ),
        Case(
            label="tile_city_z11",
            path=f"/tiles/{tile.z}/{tile.x}/{tile.y}.mvt",
            params={"z": tile.z, "x": tile.x, "y": tile.y, "sprawl": city_name},
            warm_repeats=1,
        ),
    ]


def _request_for(path: str, params: dict[str, Any]) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": urlencode(sorted(params.items())).encode("utf-8"),
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
    }
    return Request(scope)


async def _invoke_case(case: Case) -> None:
    if case.path == "/districts":
        params = case.params.copy()
        request = _request_for(case.path, params)
        await districts(request=request, **params)
        return
    if case.path.startswith("/tiles/"):
        await district_vector_tile(**case.params)
        return
    raise ValueError(f"Unsupported path {case.path}")


def _summarize_event(case: Case, attempt: int, event: dict[str, Any]) -> dict[str, Any]:
    top_stages = sorted(event.get("stages", []), key=lambda item: item.get("elapsed_ms", 0.0), reverse=True)[:5]
    return {
        "label": case.label,
        "attempt": attempt,
        "route": event.get("route"),
        "status_code": event.get("status_code"),
        "response_bytes": event.get("response_bytes"),
        "total_ms": event.get("total_ms"),
        "caches": event.get("caches", {}),
        "summary": event.get("summary", {}),
        "top_stages": top_stages,
        "all_stages": event.get("stages", []),
        "params": case.params,
    }


async def _run() -> list[dict[str, Any]]:
    logger = logging.getLogger("hilti.map_api.profile")
    logger.setLevel(logging.INFO)
    capture = ProfileCapture()
    logger.addHandler(capture)

    _load_base_dataframe()
    cases = _choose_cases()
    output: list[dict[str, Any]] = []
    for case in cases:
        total_runs = 1 + max(0, case.warm_repeats)
        for attempt in range(total_runs):
            before = len(capture.events)
            await _invoke_case(case)
            if len(capture.events) <= before:
                raise RuntimeError(f"No profile event captured for {case.label}")
            output.append(_summarize_event(case, attempt, capture.events[-1]))

    logger.removeHandler(capture)
    return output


def main() -> None:
    print(json.dumps(asyncio.run(_run()), indent=2))


if __name__ == "__main__":
    main()
