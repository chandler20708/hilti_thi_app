# Map Loading Methodology

## Problem

The original UK district map artifacts are too heavy to embed directly:

- `UK_map.html` is about `219 MB`
- the raw district GeoJSON is about `194 MB`
- even the GeoPackage is about `86 MB`

That is too expensive for a presentation-facing Streamlit interface.

## Implemented approach

The prototype uses:

1. a Leaflet map embedded inside Streamlit
2. a small local `aiohttp` service
3. viewport-based requests
4. zoom-based geometry simplification

This means the browser only requests district polygons that are relevant to the visible map extent.

## Request flow

1. The map reads current bounds and zoom.
2. It sends an async request to `/districts`.
3. The service filters the UK district layer to the requested viewport.
4. It simplifies geometry according to zoom.
5. It returns only the filtered GeoJSON.
6. The map redraws the current layer.

## Simplification profile

Current tolerances:

- zoom `<= 5`: `0.05`
- zoom `6`: `0.02`
- zoom `7`: `0.008`
- zoom `8`: `0.003`
- zoom `9`: `0.0015`
- zoom `>= 10`: `0.0005`

## Why this was chosen

This is not the most scalable GIS architecture possible, but it is the right tradeoff for the current stage:

- simple enough for a coursework/demo prototype
- fast enough to feel interactive
- clear enough to explain in a presentation
- easy to replace later with vector tiles if needed

## Future upgrades

If the app grows:

1. cache responses by rounded viewport and zoom
2. precompute zoom-band regional files
3. move to vector tiles or GeoParquet-backed spatial queries
4. add map click events back into page state
