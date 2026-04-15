from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent

DATASET_PATH = PROJECT_ROOT / "dataset2.xlsx"
DISTRICT_GPKG_PATH = PROJECT_ROOT / "UK_postcode_districts.gpkg"
CASE_STUDY_PATH = PROJECT_ROOT / "Hilti Case Study 2026.pdf"

MAP_HOST = "127.0.0.1"
MAP_PORT = 8765
