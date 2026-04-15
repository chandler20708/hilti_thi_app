import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent


def _resolve_data_path(filenames: tuple[str, ...], env_keys: tuple[str, ...]) -> Path:
    for env_key in env_keys:
        env_value = os.getenv(env_key)
        if not env_value:
            continue
        env_path = Path(env_value).expanduser()
        if env_path.exists():
            return env_path

    candidate_roots = [
        APP_ROOT / "data",
        PROJECT_ROOT / "data",
        Path.cwd() / "data",
        Path.cwd().parent / "data",
        APP_ROOT,
        PROJECT_ROOT,
        Path.cwd(),
        Path.cwd().parent,
    ]
    seen: list[Path] = []
    for root in candidate_roots:
        for filename in filenames:
            candidate = root / filename
            if candidate in seen:
                continue
            seen.append(candidate)
            if candidate.exists():
                return candidate
    return candidate_roots[0] / filenames[0]


DATASET_PATH = _resolve_data_path(("dataset2.xlsx",), ("HILTI_DATASET_PATH",))
DISTRICT_DATA_PATH = _resolve_data_path(
    ("UK_postcode_districts.parquet", "UK_postcode_districts.gpkg", "UK_postcode_districts.geojson"),
    ("HILTI_DISTRICT_PATH", "HILTI_DISTRICT_GPKG_PATH"),
)
CASE_STUDY_PATH = _resolve_data_path(("Hilti Case Study 2026.pdf",), ("HILTI_CASE_STUDY_PATH",))
