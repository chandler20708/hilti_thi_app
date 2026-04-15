from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


def _seed_from_text(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (2**32 - 1)


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(np.clip(value, low, high))


def build_synthetic_metrics(row: pd.Series) -> dict[str, object]:
    post_dist = str(row["PostDist"])
    seed = _seed_from_text(post_dist)
    rng = np.random.default_rng(seed)

    observed_flag = bool(row.get("observed_flag", False))
    observed_area = row.get("Area (sq mi)")
    observed_ratio = row.get("ratio")
    observed_territory = row.get("Territory count")

    area_sq_mi = float(observed_area) if pd.notna(observed_area) else float(np.clip(rng.lognormal(mean=3.0, sigma=0.55), 1.5, 260.0))
    territory_count = int(observed_territory) if pd.notna(observed_territory) else int(np.clip(round(rng.normal(6.5, 2.1)), 2, 14))
    ratio = float(observed_ratio) if pd.notna(observed_ratio) else float(area_sq_mi / max(territory_count, 1))

    urban_density = _clip(82 - area_sq_mi * 0.18 + rng.normal(0, 10))
    project_intensity = _clip(38 + urban_density * 0.38 + rng.normal(0, 9))
    growth_momentum = _clip(44 + urban_density * 0.26 + rng.normal(0, 11))
    accessibility_score = _clip(78 - ratio * 2.8 + rng.normal(0, 8))
    loyalty_strength = _clip(52 + rng.normal(0, 15))
    competition_pressure = _clip(30 + urban_density * 0.42 + rng.normal(0, 12))
    service_gap = _clip(62 - accessibility_score * 0.45 + rng.normal(0, 10))

    segment_mix = rng.dirichlet(
        alpha=[
            1.4 + urban_density / 55,
            1.5 + project_intensity / 50,
            1.3 + growth_momentum / 60,
        ]
    )
    enterprise_share, contractor_share, specialist_share = segment_mix
    primary_segment = (
        "Enterprise Projects"
        if enterprise_share >= contractor_share and enterprise_share >= specialist_share
        else "Growth Contractors"
        if contractor_share >= specialist_share
        else "Trade Specialists"
    )

    existing_accounts = int(np.clip(rng.normal(110 + urban_density * 2.4, 35), 30, 480))
    lead_volume = int(np.clip(rng.normal(80 + growth_momentum * 1.8, 28), 20, 420))
    segment_fit = _clip(
        22
        + enterprise_share * 34
        + contractor_share * 30
        + specialist_share * 14
        + loyalty_strength * 0.15
        + rng.normal(0, 4)
    )

    market_potential_score = _clip(
        0.33 * growth_momentum
        + 0.25 * urban_density
        + 0.22 * min(100, lead_volume / 3.0)
        + 0.20 * (100 - competition_pressure)
    )
    customer_access_score = _clip(
        0.48 * accessibility_score
        + 0.30 * (100 - min(100, ratio * 4.5))
        + 0.22 * loyalty_strength
    )
    customer_profile_score = _clip(
        0.45 * segment_fit
        + 0.30 * project_intensity
        + 0.25 * loyalty_strength
    )
    geographic_intensity_index = _clip(0.58 * growth_momentum + 0.42 * urban_density)
    project_intensity_score = _clip(0.72 * project_intensity + 0.28 * market_potential_score)

    acquisition_opportunity = _clip(
        0.42 * market_potential_score
        + 0.34 * segment_fit
        + 0.24 * (100 - competition_pressure)
    )
    retention_risk = _clip(
        0.34 * competition_pressure
        + 0.24 * (100 - loyalty_strength)
        + 0.24 * service_gap
        + 0.18 * (100 - customer_access_score)
    )
    market_opportunity_score = _clip(
        0.62 * acquisition_opportunity
        + 0.38 * (100 - retention_risk)
    )

    return {
        "data_source": "Observed workbook + synthetic augmentation" if observed_flag else "Synthetic prototype",
        "territory_count_demo": territory_count,
        "area_sq_mi_demo": area_sq_mi,
        "ratio_demo": ratio,
        "existing_accounts": existing_accounts,
        "lead_volume": lead_volume,
        "urban_density": urban_density,
        "growth_momentum": growth_momentum,
        "accessibility_score": accessibility_score,
        "competition_pressure": competition_pressure,
        "loyalty_strength": loyalty_strength,
        "service_gap": service_gap,
        "enterprise_share": float(enterprise_share),
        "contractor_share": float(contractor_share),
        "specialist_share": float(specialist_share),
        "primary_segment": primary_segment,
        "segment_fit": segment_fit,
        "mps": market_potential_score,
        "cas": customer_access_score,
        "cps": customer_profile_score,
        "gii": geographic_intensity_index,
        "pis": project_intensity_score,
        "acquisition_opportunity": acquisition_opportunity,
        "retention_risk": retention_risk,
        "market_opportunity_score": market_opportunity_score,
    }
