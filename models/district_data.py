from __future__ import annotations

from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from pyogrio.errors import DataSourceError

from config import DATASET_PATH, DISTRICT_GPKG_PATH
from .synthetic_portfolio import build_synthetic_metrics


def _percentile_skew(series: pd.Series, exponent: float = 2.35) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return series

    percentile = valid.rank(method="average", pct=True).clip(0.0, 1.0)
    skewed = (percentile ** exponent) * 100.0

    result = pd.Series(np.nan, index=series.index, dtype="float64")
    result.loc[valid.index] = skewed
    return result


@lru_cache(maxsize=1)
def load_observed_metrics() -> pd.DataFrame:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATASET_PATH}. Set HILTI_DATASET_PATH or place dataset2.xlsx in the project root."
        )
    df = pd.read_excel(DATASET_PATH)
    df["Postal District"] = df["Postal District"].astype(str).str.upper().str.strip()
    return df


@lru_cache(maxsize=1)
def load_prototype_geo_dataframe() -> gpd.GeoDataFrame:
    if not DISTRICT_GPKG_PATH.exists():
        raise FileNotFoundError(
            f"District geopackage not found at {DISTRICT_GPKG_PATH}. Set HILTI_DISTRICT_GPKG_PATH or place UK_postcode_districts.gpkg in the project root."
        )
    try:
        geo = gpd.read_file(DISTRICT_GPKG_PATH).to_crs(4326)
    except DataSourceError as error:
        raise RuntimeError(
            f"Unable to open district geopackage at {DISTRICT_GPKG_PATH}. Confirm the file was uploaded to the deployment and is a valid .gpkg."
        ) from error
    geo["PostDist"] = geo["PostDist"].astype(str).str.upper().str.strip()

    observed = load_observed_metrics().copy()
    observed["observed_flag"] = True

    merged = geo.merge(
        observed,
        left_on="PostDist",
        right_on="Postal District",
        how="left",
    )
    merged["observed_flag"] = merged["observed_flag"].astype("boolean").fillna(False).astype(bool)

    synthetic_rows = merged.apply(build_synthetic_metrics, axis=1, result_type="expand")
    merged = pd.concat([merged, synthetic_rows], axis=1)

    merged["retention_health"] = 100.0 - merged["retention_risk"]
    merged["market_opportunity_raw_score"] = merged["market_opportunity_score"]
    merged["market_opportunity_score"] = _percentile_skew(merged["market_opportunity_score"])

    points = merged.geometry.representative_point()
    merged["center_lat"] = points.y
    merged["center_lon"] = points.x
    merged["label"] = merged["PostDist"].fillna("Unknown")

    return gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")


def get_filter_options(gdf: gpd.GeoDataFrame) -> dict[str, list[str]]:
    return {
        "districts": ["All"] + sorted(gdf["PostDist"].dropna().unique().tolist()),
        "post_areas": ["All"] + sorted(gdf["PostArea"].dropna().unique().tolist()),
        "sprawls": ["All"] + sorted(gdf["Sprawl"].dropna().unique().tolist()),
        "segments": ["All"] + sorted(gdf["primary_segment"].dropna().unique().tolist()),
    }
