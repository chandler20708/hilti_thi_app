from __future__ import annotations

from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from pyogrio.errors import DataSourceError

from api.profiling import RequestProfile
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

# Optional columns written by ``scripts/enrich_district_geometries.py`` (coarser WGS84
# polygons built offline so runtime simplify + RAM stay lower).
GEOM_MAP_LOW = "geom_map_low"
GEOM_MAP_MID = "geom_map_mid"
SIZE_CLASS_ORDER = ["A", "B", "C", "D", "E"]
ACTIVITY_CLASS_ORDER = ["FTC", "EFA", "E", "F", "A", "P", "Non-EFA", "Focus"]
SEGMENT_MODE_ALIASES = {
    "primary_segment": "primary_segment",
    "size_class": "size_class",
    "activity_class": "activity_class",
    # Backward-compatible aliases for earlier prototype terminology.
    "customer_class": "size_class",
    "engagement_mode": "activity_class",
}
SEGMENT_MODE_COLUMNS = {
    "primary_segment": "primary_segment",
    "size_class": "size_class",
    "activity_class": "activity_class",
}
SEGMENT_MODE_LABELS = {
    "primary_segment": "Primary Segment",
    "size_class": "Size Class",
    "activity_class": "Activity Class",
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


def resolve_segment_mode(segment_mode: str | None) -> str:
    if segment_mode is None:
        return "primary_segment"
    return SEGMENT_MODE_ALIASES.get(str(segment_mode), "primary_segment")


def _size_class(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    result = pd.Series("E", index=series.index, dtype="object")
    if valid.empty:
        return result

    percentile = valid.rank(method="average", pct=True)
    result.loc[percentile[percentile >= 0.20].index] = "D"
    result.loc[percentile[percentile >= 0.40].index] = "C"
    result.loc[percentile[percentile >= 0.60].index] = "B"
    result.loc[percentile[percentile >= 0.80].index] = "A"
    return result


def _activity_class(
    existing_accounts: pd.Series,
    lead_volume: pd.Series,
    loyalty_strength: pd.Series,
    market_opportunity_score: pd.Series,
) -> pd.Series:
    existing = existing_accounts.fillna(0.0)
    leads = lead_volume.fillna(0.0)
    loyalty = loyalty_strength.fillna(0.0)
    opportunity = market_opportunity_score.fillna(0.0)
    total = (existing + leads).replace(0, 1.0)
    lead_share = leads / total
    existing_pct = existing.rank(method="average", pct=True)
    lead_pct = leads.rank(method="average", pct=True)
    loyalty_pct = loyalty.rank(method="average", pct=True)
    opportunity_pct = opportunity.rank(method="average", pct=True)
    activity_score = 0.45 * existing_pct + 0.35 * loyalty_pct + 0.20 * lead_pct

    result = pd.Series("Non-EFA", index=existing_accounts.index, dtype="object")
    result.loc[(lead_share >= 0.54) & (lead_pct >= 0.52) & (existing_pct < 0.58)] = "FTC"
    result.loc[(activity_score < 0.22) | ((existing_pct < 0.24) & (lead_pct < 0.24))] = "P"
    result.loc[(loyalty_pct >= 0.78) & (existing_pct >= 0.72) & (activity_score >= 0.72)] = "EFA"
    result.loc[(loyalty_pct >= 0.68) & (result == "Non-EFA")] = "E"
    result.loc[(existing_pct >= 0.62) & (result == "Non-EFA")] = "F"
    result.loc[(activity_score >= 0.45) & (result == "Non-EFA")] = "A"
    result.loc[(opportunity_pct >= 0.86) & (activity_score >= 0.38) & (result != "FTC")] = "Focus"
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
    merged["size_class"] = _size_class(merged["market_opportunity_score"])
    merged["activity_class"] = _activity_class(
        merged["existing_accounts"],
        merged["lead_volume"],
        merged["loyalty_strength"],
        merged["market_opportunity_score"],
    )

    merged["retention_health"] = 100.0 - merged["retention_risk"]
    merged["market_opportunity_raw_score"] = merged["market_opportunity_score"]
    merged["market_opportunity_score"] = _percentile_skew(merged["market_opportunity_score"])

    points = merged.geometry.representative_point()
    merged["center_lat"] = points.y
    merged["center_lon"] = points.x
    merged["label"] = merged["PostDist"].fillna("Unknown")

    return gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")


def get_filter_options(gdf: gpd.GeoDataFrame) -> dict[str, list[str]]:
    size_labels = set(gdf["size_class"].dropna().unique()) if "size_class" in gdf.columns else set()
    activity_labels = set(gdf["activity_class"].dropna().unique()) if "activity_class" in gdf.columns else set()
    return {
        "districts": ["All"] + sorted(gdf["PostDist"].dropna().unique().tolist()),
        "sprawls": ["All"] + sorted(gdf["Sprawl"].dropna().unique().tolist()),
        "segments": ["All"] + sorted(gdf["primary_segment"].dropna().unique().tolist()),
        "segment_modes": SEGMENT_MODE_LABELS,
        "segments_by_mode": {
            "primary_segment": ["All"] + sorted(gdf["primary_segment"].dropna().unique().tolist()),
            "size_class": ["All"] + [label for label in SIZE_CLASS_ORDER if label in size_labels],
            "activity_class": ["All"] + [label for label in ACTIVITY_CLASS_ORDER if label in activity_labels],
        },
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
        if GEOM_MAP_MID in gdf.columns and row_count > 180:
            frame["geometry"] = gdf.loc[frame.index, GEOM_MAP_MID]
        else:
            if row_count > 700:
                tolerance = 0.018
            elif row_count > 400:
                tolerance = 0.012
            elif row_count > 220:
                tolerance = 0.006
            elif row_count > 120:
                tolerance = 0.004
            else:
                tolerance = 0.0015
            frame["geometry"] = frame.geometry.simplify(tolerance=tolerance, preserve_topology=True)
    frame = frame.rename(columns=MAP_PAYLOAD_RENAMES)
    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")


def api_geometry_series(gdf: gpd.GeoDataFrame, zoom: int) -> gpd.GeoSeries:
    if GEOM_MAP_LOW in gdf.columns and zoom <= 6:
        return gdf[GEOM_MAP_LOW]
    if GEOM_MAP_MID in gdf.columns and zoom <= 9:
        return gdf[GEOM_MAP_MID]
    return gdf.geometry


def build_api_map_frame(
    gdf: gpd.GeoDataFrame,
    zoom: int,
    *,
    allow_centroid_fallback: bool = True,
    profile: RequestProfile | None = None,
) -> gpd.GeoDataFrame:
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
    frame = gdf.loc[:, available_columns].copy()
    row_count = len(frame)
    # Prefer filled polygons; centroids only when counts stay extreme at low zoom even
    # after the strongest simplify caps above. MVT clients need polygons, so they pass
    # ``allow_centroid_fallback=False``.
    use_point_overview = allow_centroid_fallback and (
        row_count > 3800 or (zoom <= 5 and row_count > 2600)
    )
    if use_point_overview:
        if profile is not None:
            with profile.stage("representative_point", rows_before=len(gdf), rows_after_default=len(frame)) as stage:
                frame["geometry"] = gpd.points_from_xy(
                    gdf.loc[frame.index, "center_lon"],
                    gdf.loc[frame.index, "center_lat"],
                    crs="EPSG:4326",
                )
                stage.update_meta(reason="point_overview", source="precomputed_center")
        else:
            frame["geometry"] = gpd.points_from_xy(
                gdf.loc[frame.index, "center_lon"],
                gdf.loc[frame.index, "center_lat"],
                crs="EPSG:4326",
            )
        geometry_source = "precomputed_center_point"
    else:
        if profile is not None:
            profile.add_stage(
                "representative_point",
                rows_before=len(gdf),
                rows_after=len(frame),
                meta={"skipped": True, "reason": "polygon_mode"},
            )
        frame["geometry"] = api_geometry_series(gdf, zoom).loc[frame.index]
        geometry_source = "precomputed_lod" if zoom <= 9 else "base_geometry"

    if profile is not None:
        profile.add_stage(
            "simplify",
            rows_before=len(gdf),
            rows_after=len(frame),
            meta={"skipped": True, "reason": "no_runtime_simplify"},
        )
        with profile.stage("geometry_prep", rows_before=len(gdf), rows_after_default=len(frame)) as stage:
            frame = frame.rename(columns=MAP_PAYLOAD_RENAMES)
            numeric_columns = [column for column in frame.columns if column != "geometry"]
            for column in numeric_columns:
                if str(frame[column].dtype).startswith(("float", "int")):
                    frame[column] = frame[column].round(2)
            stage.update_meta(geometry_source=geometry_source, allow_centroid_fallback=allow_centroid_fallback, zoom=zoom)
    else:
        frame = frame.rename(columns=MAP_PAYLOAD_RENAMES)
        numeric_columns = [column for column in frame.columns if column != "geometry"]
        for column in numeric_columns:
            if str(frame[column].dtype).startswith(("float", "int")):
                frame[column] = frame[column].round(2)

    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")
