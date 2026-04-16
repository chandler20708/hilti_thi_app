# Hilti Territory Growth Dashboard

This folder now contains a manager-facing Streamlit dashboard organised around a clearer application structure:

- `models/` for data preparation and scoring logic
- `components/` for reusable UI pieces, styling, and map rendering
- `controllers/` for filtering and page orchestration helpers
- `screens/` for full-screen render modules
- `docs/` for methodology and research notes
- `data/` for deployable runtime data assets

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

The app uses `Overview.py` as the main executive dashboard entrypoint and `pages/` for supporting Streamlit pages such as methodology notes.

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
- runtime data files are resolved from `data/` first, then legacy fallback paths

### Runtime data assets

The deployable data bundle now lives in the app-local `data/` folder:

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

The UK district boundary file is too heavy to keep as raw HTML or GeoJSON assets in the repository. The app therefore uses:

1. an embedded Leaflet component inside Streamlit
2. filtered GeoDataFrame scope serialized directly to GeoJSON
3. compressed GeoParquet as the primary runtime boundary asset
4. client-side rendering for map styling and overlays

The deployed app now uses compressed GeoParquet in `data/UK_postcode_districts.parquet` as the primary runtime boundary asset.

See [docs/MAP_LOADING_METHODOLOGY.md](./docs/MAP_LOADING_METHODOLOGY.md) for the full explanation.

## THI methodology notes

The current scoring model still uses a weighted-sum MCDA prototype so the ranking pipeline is concrete and discussable now. It is meant to be tightened after stakeholder review.

See [docs/THI_PROTOTYPE_METHODOLOGY.md](./docs/THI_PROTOTYPE_METHODOLOGY.md).

## Run

From the app root:

```bash
source .venv/bin/activate
streamlit run Overview.py
```

## Dependencies

Install app-specific dependencies with:

```bash
pip install -r requirements.txt
```

## Streamlit Cloud deployment

In the normal case, no secrets are required as long as the app-local `data/` folder is committed with the app.

If you want the fast viewport-loading map in deployment, host the FastAPI service separately and set `API_BASE_URL` in Streamlit Cloud. You can still run the Streamlit app without it, but the map will fall back to the inline mode.

If you need to override the paths in Streamlit Cloud, use TOML secrets like this:

```toml
HILTI_DATASET_PATH = "/mount/src/data/dataset2.xlsx"
HILTI_DISTRICT_PATH = "/mount/src/data/UK_postcode_districts.parquet"
HILTI_CASE_STUDY_PATH = "/mount/src/data/Hilti Case Study 2026.pdf"
API_BASE_URL = "https://your-map-api.example.com"
```

## Optional FastAPI map service

The repository includes a FastAPI backend at `api/main.py` for viewport-based district loading.

Run it locally from the app root with:

```bash
uvicorn api.main:app --reload
```

For hosted deployments, set:

- `API_BASE_URL` in Streamlit Cloud secrets
- `API_CORS_ORIGINS` in the FastAPI host environment

For a demo or personal project, `API_CORS_ORIGINS="*"` is fine. For a stricter setup, set it to your Streamlit app URL.

### Free-tier cold starts (GitHub keep-warm)

The workflow `.github/workflows/keep-warm.yml` runs on a cron schedule and **GET**s your endpoints after a **random 0–45 minute** delay so wake times vary. Add **repository Action secrets**:

- **`KEEP_WARM_API_URL`** — e.g. `https://your-service.onrender.com/health` (required for API wake)
- **`KEEP_WARM_STREAMLIT_URL`** — your Streamlit app URL (optional)

Scheduled workflows only run on the **default** branch and GitHub may **disable** them after long repository inactivity; re-enable under **Actions** if needed.

The FastAPI service also **caches identical `/districts` query strings** for about 90 seconds (bounded memory) and enables **gzip** for JSON responses to reduce transfer time.

## Next steps after the meeting

1. Replace the provisional factor names and weights with the agreed THI framework.
2. Decide which fields can remain synthetic in demos and which must be hidden.
3. Confirm whether Market Opportunity should prioritise acquisition, retention, or a combined story.
4. Decide whether THI should remain a weighted-sum MCDA model or whether the final deliverable should include AHP/TOPSIS-style research validation.
