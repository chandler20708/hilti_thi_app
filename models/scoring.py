from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FactorDefinition:
    key: str
    label: str
    column: str
    higher_is_better: bool
    description: str


FACTOR_DEFINITIONS: tuple[FactorDefinition, ...] = (
    FactorDefinition("mps", "MPS", "mps", True, "Prototype market potential score."),
    FactorDefinition("cas", "CAS", "cas", True, "Prototype customer accessibility score."),
    FactorDefinition("cps", "CPS", "cps", True, "Prototype customer profile strength score."),
    FactorDefinition("gii", "GII", "gii", True, "Prototype geographic intensity index."),
    FactorDefinition("pis", "PIS", "pis", True, "Prototype project intensity score."),
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "mps": 0.25,
    "cas": 0.20,
    "cps": 0.14,
    "gii": 0.21,
    "pis": 0.20,
}


def factor_catalog() -> tuple[FactorDefinition, ...]:
    return FACTOR_DEFINITIONS


def _normalize(series: pd.Series, higher_is_better: bool) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index, dtype="float64")

    # Percentile normalization separates territories more clearly than plain
    # min-max scaling, which can compress most districts into the middle band.
    normalized = valid.rank(method="average", pct=True)
    if not higher_is_better:
        normalized = 1.0 - normalized

    result = pd.Series(np.nan, index=series.index, dtype="float64")
    result.loc[valid.index] = normalized
    return result


def _contrast_stretch(series: pd.Series, exponent: float = 0.82) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return series

    centered = (valid * 2.0) - 1.0
    stretched = np.sign(centered) * (np.abs(centered) ** exponent)
    output = ((stretched + 1.0) / 2.0).clip(0.0, 1.0)

    result = pd.Series(np.nan, index=series.index, dtype="float64")
    result.loc[valid.index] = output
    return result


def score_thi(gdf: gpd.GeoDataFrame, weights: dict[str, float], active_keys: list[str]) -> gpd.GeoDataFrame:
    scored = gdf.copy()
    chosen = [factor for factor in FACTOR_DEFINITIONS if factor.key in active_keys]
    if not chosen:
        chosen = list(FACTOR_DEFINITIONS)

    total_weight = sum(max(0.0, float(weights.get(factor.key, 0.0))) for factor in chosen)
    if total_weight <= 0:
        normalized_weights = {factor.key: 1 / len(chosen) for factor in chosen}
    else:
        normalized_weights = {
            factor.key: max(0.0, float(weights.get(factor.key, 0.0))) / total_weight
            for factor in chosen
        }

    valid_any = pd.Series(False, index=scored.index)
    scored["thi_score"] = 0.0

    for factor in chosen:
        component = _normalize(scored[factor.column], factor.higher_is_better)
        scored[f"{factor.key}_component"] = component
        valid_any = valid_any | component.notna()
        scored["thi_score"] = scored["thi_score"] + component.fillna(0.0) * normalized_weights[factor.key]

    scored.loc[valid_any, "thi_raw_score"] = scored.loc[valid_any, "thi_score"]
    scored["thi_score"] = _contrast_stretch(_normalize(scored["thi_score"], higher_is_better=True)) * 100.0
    scored.loc[~valid_any, "thi_score"] = np.nan
    scored.loc[~valid_any, "thi_raw_score"] = np.nan
    return scored


def summarize_metric(gdf: pd.DataFrame, metric_key: str) -> dict[str, object]:
    valid = gdf.loc[gdf[metric_key].notna()].copy()
    if valid.empty:
        return {
            "count": 0,
            "mean_value": None,
            "top_district": None,
            "top_value": None,
        }

    top_row = valid.sort_values(metric_key, ascending=False).iloc[0]
    return {
        "count": int(valid["PostDist"].nunique()),
        "mean_value": float(valid[metric_key].mean()),
        "top_district": str(top_row["PostDist"]),
        "top_value": float(top_row[metric_key]),
    }
