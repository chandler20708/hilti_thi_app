#!/usr/bin/env python3
"""Add ``geom_map_low`` and ``geom_map_mid`` to the raw UK district parquet.

These offline-simplified geometries reduce CPU, RAM, and JSON size when the app
(or MVT tiles) renders national / wide views.

Run from the app root (with dependencies installed)::

    python scripts/enrich_district_geometries.py

By default this backs up ``data/UK_postcode_districts.parquet`` to
``data/UK_postcode_districts.parquet.bak`` then overwrites the parquet in place.
Override with ``HILTI_DISTRICT_PATH`` pointing at the file to rewrite.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]

import geopandas as gpd  # noqa: E402

GEOM_MAP_LOW = "geom_map_low"
GEOM_MAP_MID = "geom_map_mid"


def main() -> None:
    path = Path(os.environ.get("HILTI_DISTRICT_PATH", _APP_ROOT / "data" / "UK_postcode_districts.parquet"))
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    print(f"Backup written to {backup}")

    geo = gpd.read_parquet(path)
    geo = geo.set_crs(4326) if geo.crs is None else geo.to_crs(4326)
    geo[GEOM_MAP_LOW] = geo.geometry.simplify(0.11, preserve_topology=True)
    geo[GEOM_MAP_MID] = geo.geometry.simplify(0.028, preserve_topology=True)
    geo.to_parquet(path, index=False)
    print(f"Updated {path} with {GEOM_MAP_LOW} and {GEOM_MAP_MID}.")


if __name__ == "__main__":
    main()
