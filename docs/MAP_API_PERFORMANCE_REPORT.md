# Map API Performance Report

Date: 2026-04-16

Profiling was run with `HILTI_PROFILE_MAP_API=1` using `scripts/profile_map_api.py`, which exercises the real FastAPI handlers in-process and captures structured per-request timing logs.

Representative requests:

1. National-ish low zoom: `/districts` with near-national bbox at `zoom=5`
2. Medium city viewport: `/districts` for London at `zoom=9`
3. Narrow local viewport: `/districts` for `EC1Y` in London at `zoom=12`
4. One MVT tile in city viewport: `/tiles/11/1023/681.mvt?sprawl=London`

## Baseline Before Fixes

| Request | Total ms | Response bytes | Top stages |
| --- | ---: | ---: | --- |
| `/districts` national low zoom | 81.6 | 1,330,138 | serialization 49.7, representative_point 17.7, scoring 6.5 |
| `/districts` medium city | 13.5 | 179,260 | serialization 8.8, precise_intersects 1.0, filtering 0.8 |
| `/districts` narrow local | 3.4 | 5,788 | filtering 0.7, geometry_prep 0.6, serialization 0.5 |
| `/tiles` city z11 tile | 92.6 | 82,131 | MVT encode 74.7, CRS transform 11.4, feature prep 2.3 |

Observed baseline facts:

- `/districts` was already using `orjson` GeoJSON serialization, not GeoPandas `.to_json()`.
- Runtime `simplify()` was not active in the profiled `/districts` or `/tiles` path. The `simplify` stage was consistently `0 ms` and logged as skipped.
- `/tiles` was slower than `/districts` primarily because one tile request still did full per-tile geometry prep, `to_crs(3857)`, and encode, with encode dominating.

## Targeted Changes Implemented

1. Added request-scoped structured profiling behind `HILTI_PROFILE_MAP_API=1`
2. Reused precomputed `center_lat` / `center_lon` for low-zoom point-overview geometry instead of calling `geometry.representative_point()` per request
3. Reworked GeoJSON serialization to avoid `namedtuple._asdict()` on every row and added a fast path for `Point` geometry encoding
4. Extended MVT precomputed LOD usage so `geom_map_mid` is used through `z <= 11`, reducing tile geometry complexity before `to_crs()` and encode

## Results After Fixes

| Request | Total ms | Response bytes | Change |
| --- | ---: | ---: | --- |
| `/districts` national low zoom | 62.8 | 1,330,138 | `-23%` latency |
| `/districts` medium city | 12.0 | 179,260 | `-11%` latency |
| `/districts` narrow local | 3.6 | 5,788 | effectively unchanged |
| `/tiles` city z11 tile | 30.1 | 7,957 | `-68%` latency, `-90%` bytes |

Key after-fix stage timings:

- `/districts` national low zoom: serialization 45.9 ms, scoring 6.0 ms, point geometry prep 3.0 ms
- `/districts` medium city: serialization 8.7 ms, filtering 0.7 ms, geometry prep 0.6 ms
- `/tiles` city z11 tile: geometry prep 11.1 ms, MVT encode 10.1 ms, CRS transform 4.5 ms

## Top Contributors

### `/districts`

1. GeoJSON serialization
2. Low-zoom point geometry creation for national views
3. THI scoring on scoring-cache miss
4. Filtering when cache-miss and viewport is selective
5. Precise intersects for zoomed-in polygon views

### `/tiles`

1. MVT encode
2. Geometry selection / frame materialization
3. `to_crs(3857)`
4. Feature-property preparation
5. Filtering and precise intersects

## Complexity Notes

- Scoring: `O(n)` over all districts
- Filtering: `O(n)` over all districts
- GeoJSON serialization: `O(n)` over returned rows and output fields
- BBox sindex: roughly `O(log n + k)`
- Precise intersects: `O(k)` over candidate rows after sindex
- CRS transform: `O(k * vertices)`
- MVT encode: `O(k * vertices)` and repeated per tile
- Tile mode multiplies work by tile count: the full filter/clip/geometry/CRS/encode chain is repeated for every tile request even when scoring is cached

## Cache Findings

Exact-repeat behavior:

- District response cache is very effective on identical repeat requests: national `81.6 ms -> 0.05 ms`, medium city `13.5 ms -> 0.04 ms`, local `3.4 ms -> 0.03 ms`
- MVT cache is also very effective on exact repeat: `92.6 ms -> 0.04 ms` before fixes, `30.1 ms -> 0.05 ms` after fixes

Interaction-pattern checks:

- Single-entry scoring cache is fragile for alternating weight or active-key combinations. In an alternating London viewport check, every changed weight/active combination caused a scoring-cache miss.
- Filtered-frame cache materially helps `/districts` across pans with the same filters but different bbox values. In a London pan check, a second bbox with the same `sprawl=London` filter missed the districts-response cache but hit the filtered-frame cache and dropped request time from `25.5 ms` to `11.9 ms`.
- Filtered-frame caching would help `/tiles` somewhat, but filtering was under `1 ms` in the measured tile request, so it is not the primary MVT lever.

## Investigation Answers

1. Biggest latency contributor in `/districts`: GeoJSON serialization. On the baseline national request it was `49.7 ms / 81.6 ms`; on the medium city request it was `8.8 ms / 13.5 ms`.
2. Biggest latency contributor in `/tiles`: MVT encode. On the baseline city tile it was `74.7 ms / 92.6 ms`.
3. Is serialization slower than geometry processing? For `/districts`, yes. Serialization dominated all measured `/districts` cases. For `/tiles`, encode + CRS dominated more than filtering/intersects.
4. Is runtime simplify still materially hurting performance? No. It was not on the active request path in the measured runs.
5. Are cache sizes too small relative to real interaction patterns? The single-entry scoring cache is too small for alternating weight/active configurations. The districts-response cache is fine for exact repeats but does not help across pans. The filtered-frame cache is useful across pans.
6. Would filtered-frame caching materially help? Yes for `/districts` pan patterns; only modestly for `/tiles`, where encode and CRS dominate.
7. Is MVT slower mainly because of per-tile repeated work, not encoding itself? Both matter, but encoding itself was the largest per-tile cost. The bigger user-visible slowdown is that this expensive per-tile work is repeated for multiple tiles.

## Recommended Next Steps

- Keep profiling enabled in staging while validating real interaction traces
- Consider a small scoring-cache LRU only if memory headroom is confirmed on Render-like hosts
- Only add filtered-frame caching to `/tiles` if real multi-tile traces show filter cost accumulating enough to matter
- Do not spend more time on `intersects` or runtime simplify unless new measurements show a different workload shape
