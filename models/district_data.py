from __future__ import annotations

from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from pyogrio.errors import DataSourceError

from config import DATASET_PATH, DISTRICT_DATA_PATH
from .synthetic_portfolio import build_synthetic_metrics

MAP_PAYLOAD_COLUMNS = [
    "PostDist",
    "market_opportunity_score",
    "retention_health",
    "competition_pressure",
    "primary_segment",
    "lead_volume",
    "existing_accounts",
    "center_lat",
    "center_lon",
    "data_source",
]

MAP_PAYLOAD_RENAMES = {
    "PostDist": "post_dist",
    "PostArea": "post_area",
    "Sprawl": "sprawl",
}


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
    if not DISTRICT_DATA_PATH.exists():
        raise FileNotFoundError(
            f"District geometry not found at {DISTRICT_DATA_PATH}. Place UK_postcode_districts.parquet in the data folder, or set HILTI_DISTRICT_PATH."
        )
    try:
        if DISTRICT_DATA_PATH.suffix.lower() == ".parquet":
            geo = gpd.read_parquet(DISTRICT_DATA_PATH)
        else:
            geo = gpd.read_file(DISTRICT_DATA_PATH)
        geo = geo.set_crs(4326) if geo.crs is None else geo.to_crs(4326)
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(
            "Unable to read district parquet data. Ensure pyarrow is installed in the deployment environment."
        ) from error
    except DataSourceError as error:
        raise RuntimeError(
            f"Unable to open district geometry at {DISTRICT_DATA_PATH}. Confirm the file was uploaded to the deployment and is a valid geopackage or parquet file."
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
        "sprawls": ["All"] + sorted(gdf["Sprawl"].dropna().unique().tolist()),
        "segments": ["All"] + sorted(gdf["primary_segment"].dropna().unique().tolist()),
    }


def build_map_frame(gdf: gpd.GeoDataFrame, city_scope: str) -> gpd.GeoDataFrame:
    available_columns = [column for column in MAP_PAYLOAD_COLUMNS if column in gdf.columns]
    frame = gdf.loc[:, available_columns + ["geometry"]].copy()
    row_count = len(frame)

    # National overview has to stay small enough for Streamlit Cloud message limits.
    use_point_overview = city_scope == "All" or row_count > 900
    if use_point_overview:
        frame["geometry"] = frame.geometry.representative_point()
    else:
        if row_count > 300:
            tolerance = 0.01
        elif row_count > 120:
            tolerance = 0.004
        else:
            tolerance = 0.0015
        frame["geometry"] = frame.geometry.simplify(tolerance=tolerance, preserve_topology=True)

    frame = frame.rename(columns=MAP_PAYLOAD_RENAMES)
    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")


def map_simplification_tolerance(zoom: int) -> float:
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


def build_api_map_frame(gdf: gpd.GeoDataFrame, zoom: int) -> gpd.GeoDataFrame:
    export_columns = [
        "PostDist",
        "PostArea",
        "Sprawl",
        "primary_segment",
        "data_source",
        "center_lat",
        "center_lon",
        "market_opportunity_score",
        "acquisition_opportunity",
        "retention_risk",
        "retention_health",
        "competition_pressure",
        "existing_accounts",
        "lead_volume",
        "thi_score",
    ]
    available_columns = [column for column in export_columns if column in gdf.columns]
    frame = gdf.loc[:, available_columns + ["geometry"]].copy()
    frame["geometry"] = frame.geometry.simplify(
        tolerance=map_simplification_tolerance(zoom),
        preserve_topology=True,
    )
    frame = frame.rename(columns=MAP_PAYLOAD_RENAMES)

    numeric_columns = [column for column in frame.columns if column != "geometry"]
    for column in numeric_columns:
        if str(frame[column].dtype).startswith(("float", "int")):
            frame[column] = frame[column].round(2)

    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")
