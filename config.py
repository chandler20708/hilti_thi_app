import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent


def _resolve_data_path(filename: str, env_key: str) -> Path:
    env_value = os.getenv(env_key)
    if env_value:
        env_path = Path(env_value).expanduser()
        if env_path.exists():
            return env_path

    candidates = [
        PROJECT_ROOT / filename,
        APP_ROOT / filename,
        Path.cwd() / filename,
        Path.cwd().parent / filename,
    ]
    seen: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.append(candidate)
        if candidate.exists():
            return candidate
    return candidates[0]


DATASET_PATH = _resolve_data_path("dataset2.xlsx", "HILTI_DATASET_PATH")
DISTRICT_GPKG_PATH = _resolve_data_path("UK_postcode_districts.gpkg", "HILTI_DISTRICT_GPKG_PATH")
CASE_STUDY_PATH = _resolve_data_path("Hilti Case Study 2026.pdf", "HILTI_CASE_STUDY_PATH")

MAP_HOST = "127.0.0.1"
MAP_PORT = 8765
