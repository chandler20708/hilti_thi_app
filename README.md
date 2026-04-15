# Hilti Territory Growth Dashboard

This folder now contains a manager-facing Streamlit dashboard organised around a clearer application structure:

- `models/` for data preparation and scoring logic
- `views/` for page rendering, styling, and interactive components
- `controllers/` for filtering and page orchestration helpers
- `services/` for the local async map API
- `docs/` for methodology and research notes
- `../data/` for deployable runtime data assets

The app is still a prototype. The scoring logic and several commercial signals remain provisional, and some Hilti-facing metrics still rely on synthetic augmentation because of access and confidentiality limits.

## Why the structure changed

The earlier prototype was useful for getting the map working, but it was not the right shape once you asked for:

- simple multipage navigation
- a dashboard-style executive landing page
- THI controls without a separate redundant page
- synthetic data support
- clearer naming than `backend` / `frontend`

This version is therefore closer to a lightweight MVC-style application structure, without overengineering the project.

## Streamlit approach

The app now uses the standard `app.py` plus `pages/` convention:

- `app.py` is the default executive dashboard entrypoint
- `pages/` contains supporting reference pages such as methodology notes

## Pages

### 1. Executive Dashboard

This is the default landing page. It is built to answer a manager question quickly:

- choose a city
- browse the full city footprint on the map
- switch between growth opportunity and retention health
- use the top 5 territories as a reference summary, not the main interaction surface
- open a territory action view with plain-language guidance

### 2. Methodology Notes

Provides the supporting explanation for:

- provisional scoring logic
- synthetic augmentation
- factor naming
- current prototype constraints

## Data design

The prototype uses a hybrid data model:

- observed workbook rows are preserved where they exist
- synthetic portfolio metrics are generated for all UK districts
- runtime data files are resolved from `../data/` first, then legacy root paths

### Runtime data assets

The deployable data bundle now lives in the repository-level `data/` folder:

- `data/dataset2.xlsx`
- `data/UK_postcode_districts.parquet`
- `data/Hilti Case Study 2026.pdf`

The UK district boundaries were converted from `.gpkg` to compressed GeoParquet to reduce deployment size while keeping geometry and CRS metadata intact.

This gives the app national map coverage now, while still keeping the real available data visible where it already exists.

### Current synthetic fields include

- `market_opportunity_score`
- `acquisition_opportunity`
- `retention_risk` internally, surfaced as `retention_health` in the dashboard
- `primary_segment`
- `existing_accounts`
- `lead_volume`
- `mps`, `cas`, `cps`, `gii`, `pis`

These are placeholders for demo and research framing, not the final Hilti-approved indicators.

## Map strategy

The UK district boundary file is too heavy to embed as one static HTML asset. The app therefore uses:

1. an embedded Leaflet component inside Streamlit
2. a small local `aiohttp` service
3. viewport-based async loading
4. zoom-based geometry simplification

That lets the dashboard behave like a real app instead of trying to ship the whole boundary set to the browser on first render.

The deployed app now uses compressed GeoParquet in `data/UK_postcode_districts.parquet` as the primary runtime boundary asset.

See [docs/MAP_LOADING_METHODOLOGY.md](./docs/MAP_LOADING_METHODOLOGY.md) for the full explanation.

## THI methodology notes

The current scoring model still uses a weighted-sum MCDA prototype so the ranking pipeline is concrete and discussable now. It is meant to be tightened after stakeholder review.

See [docs/THI_PROTOTYPE_METHODOLOGY.md](./docs/THI_PROTOTYPE_METHODOLOGY.md).

## Run

From the project root:

```bash
source .venv/bin/activate
streamlit run hilti_thi_app/app.py
```

## Dependencies

Install app-specific dependencies with:

```bash
pip install -r hilti_thi_app/requirements.txt
```

## Streamlit Cloud deployment

In the normal case, no secrets are required as long as the `data/` folder is committed with the app.

If you need to override the paths in Streamlit Cloud, use TOML secrets like this:

```toml
HILTI_DATASET_PATH = "/mount/src/data/dataset2.xlsx"
HILTI_DISTRICT_PATH = "/mount/src/data/UK_postcode_districts.parquet"
HILTI_CASE_STUDY_PATH = "/mount/src/data/Hilti Case Study 2026.pdf"
```

## Next steps after the meeting

1. Replace the provisional factor names and weights with the agreed THI framework.
2. Decide which fields can remain synthetic in demos and which must be hidden.
3. Confirm whether Market Opportunity should prioritise acquisition, retention, or a combined story.
4. Decide whether THI should remain a weighted-sum MCDA model or whether the final deliverable should include AHP/TOPSIS-style research validation.
