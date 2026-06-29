from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from config import APP_ROOT


EXTERNAL_DATA_DIR = APP_ROOT / "data"


def _display_store_name(value: object) -> str:
    return str(value).replace("Hilti Store ", "Construction Hub ")


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
    if "nearest_hilti_store" in merged.columns:
        merged["nearest_hilti_store"] = merged["nearest_hilti_store"].map(_display_store_name)
    local_authority_path = _data_path("competitor_store_local_authority_lookup.csv")
    if local_authority_path.exists():
        lookup = pd.read_csv(local_authority_path).loc[
            :, ["osm_type", "osm_id", "local_authority_code", "local_authority_name"]
        ]
        merged = merged.merge(lookup, on=["osm_type", "osm_id"], how="left")
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
def load_power_tool_manufacturer_competitors() -> pd.DataFrame:
    return _read_csv("hilti_power_tool_manufacturer_competitors.csv")


@lru_cache(maxsize=1)
def load_power_tool_authorised_locations() -> pd.DataFrame:
    locations = _read_csv("hilti_power_tool_authorised_locations.csv")
    locations["distance_to_nearest_hilti_km"] = pd.to_numeric(
        locations["distance_to_nearest_hilti_km"],
        errors="coerce",
    )
    if "nearest_hilti_store" in locations.columns:
        locations["nearest_hilti_store"] = locations["nearest_hilti_store"].map(_display_store_name)
    return locations


@lru_cache(maxsize=1)
def load_power_tool_distribution_proxy() -> pd.DataFrame:
    return _read_csv("hilti_power_tool_distribution_proxy.csv")


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


def build_overview_external_context(
    hilti_store_names: tuple[str, ...] | None = None,
    local_authority_name: str | None = None,
) -> dict[str, Any]:
    stores = load_competitor_store_locations()
    demand = load_market_demand_frame()

    pressure = stores.loc[
        stores["threat_band"].isin(
            [
                "0-2 km direct local threat",
                "2-5 km strong urban overlap",
                "5-10 km metro overlap",
            ]
        )
    ].copy()
    if hilti_store_names is not None:
        pressure = pressure.loc[pressure["nearest_hilti_store"].isin(hilti_store_names)]

    if local_authority_name and local_authority_name != "All" and "local_authority_name" in stores.columns:
        authority_competitors = stores.loc[stores["local_authority_name"] == local_authority_name].copy()
        authority_label = local_authority_name
    else:
        authority_competitors = stores.copy()
        authority_label = "UK"

    authority_competitors_by_chain = (
        authority_competitors.groupby("competitor", observed=True)
        .agg(
            mapped_locations=("competitor", "size"),
            direct_threat_locations=(
                "threat_band",
                lambda values: int(
                    values.isin(
                        [
                            "0-2 km direct local threat",
                            "2-5 km strong urban overlap",
                            "5-10 km metro overlap",
                        ]
                    ).sum()
                ),
            ),
        )
        .reset_index()
        .sort_values(["mapped_locations", "competitor"], ascending=[False, True])
    )
    authority_pressure_summary = {
        "area": authority_label,
        "locations": int(len(authority_competitors)),
        "chains": int(authority_competitors["competitor"].nunique()),
        "top_competitor": (
            str(authority_competitors_by_chain.iloc[0]["competitor"])
            if not authority_competitors_by_chain.empty
            else "N/A"
        ),
    }

    pressure_by_store = (
        pressure.groupby("nearest_hilti_store", observed=True)
        .agg(
            competitor_branches_10km=("competitor", "size"),
            competitor_chains_10km=("competitor", "nunique"),
            closest_competitor_km=("distance_to_nearest_hilti_km", "min"),
        )
        .reset_index()
        .sort_values("competitor_branches_10km", ascending=False)
    )

    if pressure_by_store.empty:
        pressure_summary = {
            "store": "No local pressure",
            "branches": 0,
            "chains": 0,
            "closest_km": None,
        }
    else:
        row = pressure_by_store.iloc[0]
        pressure_summary = {
            "store": row["nearest_hilti_store"],
            "branches": int(row["competitor_branches_10km"]),
            "chains": int(row["competitor_chains_10km"]),
            "closest_km": float(row["closest_competitor_km"]),
        }

    demand_options = sorted(demand["area_name"].dropna().astype(str).unique().tolist())
    selected_name = local_authority_name if local_authority_name in demand_options else None
    if selected_name:
        selected_demand = demand.loc[demand["area_name"] == selected_name].iloc[0]
    else:
        selected_demand = demand.sort_values(
            "construction_customer_proxy_local_units_total",
            ascending=False,
        ).iloc[0]
        selected_name = str(selected_demand["area_name"])

    demand_summary = {
        "area": selected_name,
        "construction_units": int(selected_demand["construction_customer_proxy_local_units_total"]),
        "units_per_10k_people": float(selected_demand["construction_units_per_10k_people"]),
        "population": int(selected_demand["population_mid_2024"]),
    }

    return {
        "pressure_summary": pressure_summary,
        "pressure_by_store": pressure_by_store,
        "authority_pressure_summary": authority_pressure_summary,
        "authority_competitors_by_chain": authority_competitors_by_chain,
        "demand_summary": demand_summary,
        "demand_options": demand_options,
    }
