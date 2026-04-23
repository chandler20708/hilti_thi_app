from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from config import APP_ROOT


EXTERNAL_DATA_DIR = APP_ROOT / "data"


def _data_path(filename: str) -> Path:
    return EXTERNAL_DATA_DIR / filename


def _read_csv(filename: str) -> pd.DataFrame:
    path = _data_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"External market dataset not found: {path}")
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def load_competitors_master() -> pd.DataFrame:
    return _read_csv("hilti_competitors_master.csv")


@lru_cache(maxsize=1)
def load_competitor_store_locations() -> pd.DataFrame:
    stores = _read_csv("hilti_competitor_store_locations_osm.csv")
    competitors = load_competitors_master()
    merged = stores.merge(
        competitors.loc[:, ["competitor", "category", "priority", "threat_rationale"]],
        on="competitor",
        how="left",
    )
    merged["priority"] = merged["priority"].fillna("Unclassified")
    merged["category"] = merged["category"].fillna("Unclassified")
    merged["distance_to_nearest_hilti_km"] = pd.to_numeric(
        merged["distance_to_nearest_hilti_km"],
        errors="coerce",
    )
    return merged


@lru_cache(maxsize=1)
def load_population_local_authority() -> pd.DataFrame:
    population = _read_csv("uk_population_local_authority_mid2024.csv")
    population["population_mid_2024"] = pd.to_numeric(
        population["population_mid_2024"],
        errors="coerce",
    )
    return population


@lru_cache(maxsize=1)
def load_customer_proxy_summary() -> pd.DataFrame:
    proxy = _read_csv("hilti_customer_proxy_summary_by_local_authority_2025.csv")
    numeric_columns = [
        "construction_buildings_local_units",
        "civil_engineering_local_units",
        "specialised_construction_local_units",
        "construction_customer_proxy_local_units_total",
    ]
    for column in numeric_columns:
        proxy[column] = pd.to_numeric(proxy[column], errors="coerce").fillna(0)
    return proxy


@lru_cache(maxsize=1)
def load_customer_segments() -> pd.DataFrame:
    return _read_csv("hilti_customer_segments_research.csv")


@lru_cache(maxsize=1)
def load_external_source_manifest() -> dict[str, Any]:
    path = _data_path("hilti_external_dataset_sources.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_market_demand_frame() -> pd.DataFrame:
    proxy = load_customer_proxy_summary()
    population = load_population_local_authority().loc[
        :, ["area_code", "area_name", "population_mid_2024", "geography_type"]
    ]
    population = population.rename(columns={"geography_type": "population_geography_type"})
    merged = proxy.merge(
        population,
        on=["area_code", "area_name"],
        how="left",
    )
    merged["construction_units_per_10k_people"] = (
        merged["construction_customer_proxy_local_units_total"]
        / merged["population_mid_2024"].replace(0, pd.NA)
        * 10000
    )
    merged["construction_units_per_10k_people"] = merged[
        "construction_units_per_10k_people"
    ].fillna(0)
    return merged


def customer_segment_metric(segment_label: str) -> tuple[str, str]:
    if segment_label == "Building contractors":
        return "construction_buildings_local_units", "SIC 41 building contractors"
    if segment_label == "Civil engineering":
        return "civil_engineering_local_units", "SIC 42 civil engineering"
    if segment_label == "Specialist trades / MEP":
        return "specialised_construction_local_units", "SIC 43 specialist trades"
    return "construction_customer_proxy_local_units_total", "Total construction local units"
