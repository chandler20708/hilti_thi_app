# Map Loading Methodology

## Problem

The original UK district map artifacts are too heavy to embed directly:

- `UK_map.html` is about `219 MB`
- the raw district GeoJSON is about `194 MB`
- even the GeoPackage is about `86 MB`
- the compressed GeoParquet is still about `46 MB`

That is too expensive for a presentation-facing Streamlit interface.

## Implemented approach

The prototype uses:

1. a Leaflet map embedded inside Streamlit
2. direct GeoJSON injection from the current GeoDataFrame scope
3. client-side styling and interaction in Leaflet
4. local view-state persistence for recentering and zoom restore

This means the deployed app no longer depends on a localhost backend or a separate request path for district polygons.

At deployment time, the district boundary source is loaded from compressed GeoParquet in the repository `data/` folder, with legacy `.gpkg` and `.geojson` support retained as fallback.

## Request flow

1. The page filters the GeoDataFrame in Python.
2. The filtered frame is serialized to GeoJSON.
3. The GeoJSON is embedded directly in the Leaflet component.
4. Leaflet paints the polygons and overlays the store markers.
5. Zoom changes redraw the center markers locally.

## Why this was chosen

This is not the most scalable GIS architecture possible, but it is the right tradeoff for the current stage:

- simple enough for a coursework/demo prototype
- reliable in hosted Streamlit deployments
- clear enough to explain in a presentation
- easy to replace later with tiled or server-backed GIS if needed

## Future upgrades

If the app grows:

1. cache responses by rounded viewport and zoom
2. precompute zoom-band regional files
3. move to spatial indexing or vector tiles instead of loading the full national boundary layer into memory
4. add map click events back into page state
