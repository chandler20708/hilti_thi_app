from __future__ import annotations

import json
from uuid import uuid4

import streamlit.components.v1 as components


def render_leaflet_metric_map(
    geojson_data: str | None,
    metric_key: str,
    metric_label: str,
    focus_record: dict[str, object] | None,
    should_refocus: bool,
    api_base_url: str | None = None,
    filters: dict[str, object] | None = None,
    store_locations: list[dict[str, object]] | None = None,
    focus_district: str | None = None,
    weights: dict[str, float] | None = None,
    active_keys: list[str] | None = None,
    height: int = 720,
) -> None:
    map_id = f"map_{uuid4().hex}"
    state = {
        **(filters or {}),
        "metric_key": metric_key,
        "metric_label": metric_label,
        "should_refocus": should_refocus,
        "focus_district": focus_district,
        "store_locations": store_locations or [],
        "weights": weights or {},
        "active_keys": active_keys or [],
    }

    if api_base_url:
        from .shared import resolve_use_vector_tiles

        if resolve_use_vector_tiles():
            from .vector_tile_map import render_vector_tile_map

            render_vector_tile_map(
                api_base_url=api_base_url,
                metric_key=metric_key,
                metric_label=metric_label,
                focus_record=focus_record,
                should_refocus=should_refocus,
                filters=filters,
                store_locations=store_locations,
                focus_district=focus_district,
                weights=weights,
                active_keys=active_keys,
                height=height,
            )
            return

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css" />
      <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
      <style>
        html, body, #{map_id} {{
          width: 100%;
          height: {height}px;
          margin: 0;
          padding: 0;
          border-radius: 18px;
          overflow: hidden;
        }}
        .wrap {{
          position: relative;
          width: 100%;
          height: {height}px;
          overflow: hidden;
          border-radius: 18px;
          border: 1px solid rgba(16,24,40,0.08);
        }}
        .loading {{
          position: absolute;
          right: 12px;
          top: 12px;
          z-index: 999;
          background: rgba(255,255,255,0.96);
          border: 1px solid rgba(16,24,40,0.08);
          border-radius: 12px;
          padding: 7px 10px;
          font: 12px/1.3 sans-serif;
          color: #344054;
        }}
        .recenter-btn {{
          position: absolute;
          right: 12px;
          top: 48px;
          z-index: 999;
          background: rgba(17,24,39,0.94);
          color: #ffffff;
          border: none;
          border-radius: 12px;
          padding: 8px 12px;
          font: 12px/1.2 sans-serif;
          cursor: pointer;
          box-shadow: 0 8px 24px rgba(15,23,42,0.18);
        }}
        .recenter-btn:hover {{
          background: rgba(31,41,55,0.98);
        }}
        .badge {{
          position: absolute;
          left: 12px;
          top: 12px;
          z-index: 999;
          background: rgba(17,24,39,0.92);
          color: #fff;
          border-radius: 12px;
          padding: 7px 10px;
          font: 12px/1.3 sans-serif;
        }}
        .focus {{
          position: absolute;
          left: 12px;
          top: 48px;
          z-index: 999;
          background: rgba(236, 253, 243, 0.96);
          color: #027a48;
          border: 1px solid rgba(2, 122, 72, 0.16);
          border-radius: 12px;
          padding: 7px 10px;
          font: 12px/1.3 sans-serif;
          display: {{"block" if focus_record else "none"}};
        }}
        .legend {{
          background: rgba(255,255,255,0.96);
          padding: 10px 12px;
          border-radius: 12px;
          box-shadow: 0 8px 24px rgba(15,23,42,0.18);
          font: 12px/1.4 sans-serif;
        }}
        .legend-scale {{
          width: 160px;
          height: 10px;
          border-radius: 999px;
          background: linear-gradient(90deg, #ea4335 0%, #fbbc04 50%, #34a853 100%);
          margin: 8px 0 4px 0;
        }}
        .hilti-store-icon {{
          width: 22px;
          height: 22px;
          border-radius: 999px;
          background: #c8102e;
          color: #ffffff;
          border: 2px solid #ffffff;
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.24);
          display: flex;
          align-items: center;
          justify-content: center;
          font: 11px/1 sans-serif;
          font-weight: 700;
        }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="badge">Executive territory view</div>
        <div class="focus">{focus_record["label"] if focus_record and "label" in focus_record else ""}</div>
        <div id="loading" class="loading">Loading map data…</div>
        <button id="recenterBtn" class="recenter-btn">Recenter map</button>
        <div id="{map_id}"></div>
      </div>
      <script>
        const state = {json.dumps(state)};
        const focus = {json.dumps(focus_record)};
        const geojson = {geojson_data if geojson_data is not None else "null"};
        const apiBaseUrl = {json.dumps(api_base_url)};
        const storeLocations = state.store_locations || [];
        const loadingEl = document.getElementById("loading");
        const recenterBtn = document.getElementById("recenterBtn");
        const responseCache = new Map();
        const responseCacheMaxEntries = 12;
        const storageKey = "hilti_market_map_state_" + state.metric_key;
        const defaultBounds = [[49.8, -8.2], [60.9, 2.2]];

        const map = L.map("{map_id}", {{
          center: [54.5, -3.0],
          zoom: 6,
          zoomControl: true,
          zoomAnimation: false,
          fadeAnimation: false,
          markerZoomAnimation: false
        }});

        L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        const districtLayer = L.geoJSON(null, {{
          style: styleFeature,
          pointToLayer: pointToLayer,
          onEachFeature: onEachFeature
        }}).addTo(map);

        const markerLayer = L.layerGroup().addTo(map);
        const storeLayer = L.layerGroup().addTo(map);
        const storeIcon = L.divIcon({{
          className: "",
          html: '<div class="hilti-store-icon">H</div>',
          iconSize: [22, 22],
          iconAnchor: [11, 22],
          popupAnchor: [0, -20],
          tooltipAnchor: [0, -18]
        }});

        const legend = L.control({{position: "bottomright"}});
        legend.onAdd = function() {{
          const div = L.DomUtil.create("div", "legend");
          div.innerHTML = `
            <div><strong>${{state.metric_label}}</strong></div>
            <div class="legend-scale"></div>
            <div style="display:flex;justify-content:space-between;"><span>Low</span><span>High</span></div>
          `;
          return div;
        }};
        legend.addTo(map);

        function colorForMetric(value) {{
          const t = Math.max(0, Math.min(100, Number(value))) / 100;
          if (t < 0.34) return "#ea4335";
          if (t < 0.67) return "#fbbc04";
          return "#34a853";
        }}

        function styleFeature(feature) {{
          const p = feature.properties || {{}};
          if (feature.geometry && feature.geometry.type === "Point") {{
            return {{}};
          }}
          const value = p[state.metric_key];
          if (value === null || value === undefined) {{
            return {{
              color: "#98a2b3",
              weight: 0.75,
              fillColor: "#d0d5dd",
              fillOpacity: 0.12
            }};
          }}

          const highlightedDistrict = state.focus_district;
          const isFocus = highlightedDistrict && highlightedDistrict !== "All" && p.post_dist === highlightedDistrict;
          return {{
            color: isFocus ? "#101828" : "#4b2e17",
            weight: isFocus ? 2.0 : 0.8,
            fillColor: colorForMetric(value),
            fillOpacity: isFocus ? 0.74 : 0.58
          }};
        }}

        function pointToLayer(feature, latlng) {{
          const p = feature.properties || {{}};
          const value = p[state.metric_key];
          return L.circleMarker(latlng, {{
            radius: map.getZoom() >= 7 ? 5 : 3.8,
            color: "#ffffff",
            weight: 1,
            fillColor: value === null || value === undefined ? "#98a2b3" : colorForMetric(value),
            fillOpacity: 0.92
          }});
        }}

        function onEachFeature(feature, layer) {{
          const p = feature.properties || {{}};
          const metricValue = p[state.metric_key] !== null && p[state.metric_key] !== undefined ? Number(p[state.metric_key]).toFixed(1) : "N/A";
          layer.bindTooltip(`
            <div style="min-width:180px;">
              <div style="font-weight:700;margin-bottom:6px;">${{p.post_dist || "Territory"}}</div>
              <div><b>${{state.metric_label}}</b>: ${{metricValue}}</div>
              <div><b>Retention health</b>: ${{p.retention_health ?? "N/A"}}</div>
              <div><b>Competition</b>: ${{p.competition_pressure ?? "N/A"}}</div>
              <div><b>Segment</b>: ${{p.primary_segment || "N/A"}}</div>
              <div><b>Leads</b>: ${{p.lead_volume ?? "N/A"}}</div>
              <div><b>Accounts</b>: ${{p.existing_accounts ?? "N/A"}}</div>
              <div><b>Source</b>: ${{p.data_source || "N/A"}}</div>
            </div>
          `, {{sticky: true}});
        }}

        function buildQueryFromBounds(bounds, zoomOverride) {{
          const z = zoomOverride != null ? zoomOverride : map.getZoom();
          const params = new URLSearchParams();
          params.set("west", bounds.getWest().toFixed(6));
          params.set("south", bounds.getSouth().toFixed(6));
          params.set("east", bounds.getEast().toFixed(6));
          params.set("north", bounds.getNorth().toFixed(6));
          params.set("zoom", String(z));

          if (state.post_area && state.post_area !== "All") params.set("post_area", state.post_area);
          if (state.sprawl && state.sprawl !== "All") params.set("sprawl", state.sprawl);
          if (state.district && state.district !== "All") params.set("district", state.district);
          if (state.segment && state.segment !== "All") params.set("segment", state.segment);

          if (state.active_keys && state.active_keys.length) {{
            params.set("active", state.active_keys.join(","));
          }}
          if (state.weights) {{
            Object.entries(state.weights).forEach(([key, value]) => {{
              params.set(`w_${{key}}`, String(value));
            }});
          }}
          return `${{apiBaseUrl}}/districts?${{params.toString()}}`;
        }}

        function chunkGridForZoom(z) {{
          if (z <= 4) return {{ cols: 3, rows: 2 }};
          if (z <= 7) return {{ cols: 2, rows: 2 }};
          return {{ cols: 1, rows: 1 }};
        }}

        function chunkTileBounds(bounds, cols, rows) {{
          const w = bounds.getWest();
          const s = bounds.getSouth();
          const e = bounds.getEast();
          const n = bounds.getNorth();
          const dx = (e - w) / cols;
          const dy = (n - s) / rows;
          const padW = Math.max(0.0005, dx * 0.05);
          const padH = Math.max(0.0005, dy * 0.05);
          const tiles = [];
          for (let r = 0; r < rows; r++) {{
            for (let c = 0; c < cols; c++) {{
              const tw = w + c * dx - padW;
              const te = w + (c + 1) * dx + padW;
              const ts = s + r * dy - padH;
              const tn = s + (r + 1) * dy + padH;
              tiles.push(L.latLngBounds([ts, tw], [tn, te]));
            }}
          }}
          return tiles;
        }}

        function viewportMeta(bounds, zoom) {{
          const center = bounds.getCenter();
          return {{
            centerLat: center.lat,
            centerLng: center.lng,
            zoom: zoom
          }};
        }}

        function shouldCacheResponse(payload, zoom) {{
          const count = payload && payload.features ? payload.features.length : 0;
          if (zoom <= 5 && count > 1800) return false;
          return true;
        }}

        function responseCachePenalty(entry, bounds, zoom) {{
          const center = bounds.getCenter();
          const latPenalty = Math.abs((entry.centerLat || 0) - center.lat);
          const lngPenalty = Math.abs((entry.centerLng || 0) - center.lng);
          const distancePenalty = Math.sqrt((latPenalty * latPenalty) + (lngPenalty * lngPenalty));
          const zoomPenalty = Math.abs((entry.zoom || 0) - zoom) * 6;
          const agePenalty = Math.min((Date.now() - (entry.lastUsed || 0)) / 15000, 12);
          const featurePenalty = Math.min((entry.featureCount || 0) / 800, 8);
          return distancePenalty * (zoom >= 8 ? 18 : 8) + zoomPenalty + agePenalty + featurePenalty;
        }}

        function trimResponseCache(bounds, zoom) {{
          if (responseCache.size <= responseCacheMaxEntries) return;
          const ranked = Array.from(responseCache.entries()).map(([key, entry]) => {{
            return {{ key, penalty: responseCachePenalty(entry, bounds, zoom) }};
          }});
          ranked.sort((a, b) => b.penalty - a.penalty);
          while (responseCache.size > responseCacheMaxEntries && ranked.length) {{
            const evict = ranked.shift();
            responseCache.delete(evict.key);
          }}
        }}

        function getCachedResponse(key) {{
          const entry = responseCache.get(key);
          if (!entry) return null;
          entry.lastUsed = Date.now();
          responseCache.delete(key);
          responseCache.set(key, entry);
          return entry.payload;
        }}

        function setCachedResponse(key, payload, bounds, zoom) {{
          if (!shouldCacheResponse(payload, zoom)) return;
          const meta = viewportMeta(bounds, zoom);
          responseCache.set(key, {{
            payload: payload,
            centerLat: meta.centerLat,
            centerLng: meta.centerLng,
            zoom: zoom,
            featureCount: payload && payload.features ? payload.features.length : 0,
            lastUsed: Date.now()
          }});
          trimResponseCache(bounds, zoom);
        }}

        function mergeFeatureCollection(target, part, seen) {{
          const feats = part && part.features ? part.features : [];
          let added = 0;
          for (let j = 0; j < feats.length; j++) {{
            const f = feats[j];
            const id = f.properties && f.properties.post_dist;
            if (id) {{
              if (seen.has(id)) continue;
              seen.add(id);
            }}
            target.features.push(f);
            added += 1;
          }}
          return added;
        }}

        let apiRequestToken = 0;
        let apiAbort = null;
        let refreshDebounce = null;

        function scheduleRefreshFromApi() {{
          if (!apiBaseUrl) return;
          if (refreshDebounce) clearTimeout(refreshDebounce);
          refreshDebounce = setTimeout(() => {{
            refreshDebounce = null;
            refreshFromApi();
          }}, 240);
        }}

        function paint(geojson, fromRefresh) {{
            districtLayer.clearLayers();
            markerLayer.clearLayers();
            storeLayer.clearLayers();
            districtLayer.addData(geojson);

            const hasPolygonGeometry = (geojson.features || []).some((feature) => {{
              return feature.geometry && feature.geometry.type !== "Point";
            }});

            if (hasPolygonGeometry && geojson.features) {{
              geojson.features.forEach((feature) => {{
                const p = feature.properties || {{}};
                if (map.getZoom() >= 8 && p.center_lat && p.center_lon) {{
                  const marker = L.circleMarker([p.center_lat, p.center_lon], {{
                    radius: 4.5,
                    color: "#ffffff",
                    weight: 1,
                    fillColor: "#2563eb",
                    fillOpacity: 0.85
                  }});
                  marker.bindTooltip(`${{p.post_dist}}`, {{sticky: true}});
                  marker.addTo(markerLayer);
                }}
              }});
            }}

            storeLocations.forEach((store) => {{
              if (!store.latitude || !store.longitude) return;
              const marker = L.marker([store.latitude, store.longitude], {{icon: storeIcon}});
              marker.bindTooltip(store.name, {{sticky: true}});
              marker.bindPopup(`
                <div style="min-width:190px;">
                  <div style="font-weight:700;margin-bottom:6px;">${{store.name}}</div>
                  <div><b>City</b>: ${{store.city}}</div>
                  <div><b>Postcode</b>: ${{store.postcode}}</div>
                  <div style="margin-top:8px;"><a href="${{store.url}}" target="_blank" rel="noopener noreferrer">Official store page</a></div>
                </div>
              `);
              marker.addTo(storeLayer);
            }});

            const count = geojson.features ? geojson.features.length : 0;
            const mode = hasPolygonGeometry ? "districts (filled)" : "districts (overview points)";
            loadingEl.textContent = (fromRefresh ? "Refreshed " : "Loaded ") + count + " " + mode;
        }}

        async function refreshFromApi() {{
          if (!apiBaseUrl) return;
          if (apiAbort) apiAbort.abort();
          apiAbort = new AbortController();
          const signal = apiAbort.signal;
          apiRequestToken += 1;
          const myToken = apiRequestToken;

          const bounds = map.getBounds();
          const zoom = map.getZoom();
          const fullKey = buildQueryFromBounds(bounds, zoom);

          try {{
            const cached = getCachedResponse(fullKey);
            if (cached && myToken === apiRequestToken) {{
              paint(cached, true);
              return;
            }}

            const grid = chunkGridForZoom(zoom);
            if (grid.cols === 1 && grid.rows === 1) {{
              loadingEl.textContent = "Loading map data…";
              const response = await fetch(fullKey, {{ signal }});
              if (!response.ok) throw new Error("HTTP " + response.status);
              const payload = await response.json();
              if (myToken !== apiRequestToken) return;
              setCachedResponse(fullKey, payload, bounds, zoom);
              paint(payload, false);
              return;
            }}

            const tiles = chunkTileBounds(bounds, grid.cols, grid.rows);
            const merged = {{ type: "FeatureCollection", features: [] }};
            const seen = new Set();
            for (let i = 0; i < tiles.length; i++) {{
              if (myToken !== apiRequestToken) return;
              loadingEl.textContent = `Loading map data… (${{i + 1}}/${{tiles.length}})`;
              const url = buildQueryFromBounds(tiles[i], zoom);
              const response = await fetch(url, {{ signal }});
              if (!response.ok) throw new Error("HTTP " + response.status);
              const part = await response.json();
              const added = mergeFeatureCollection(merged, part, seen);
              if (myToken !== apiRequestToken) return;
              if (added > 0) {{
                paint(merged, i > 0);
                loadingEl.textContent = `Loading map data… (${{i + 1}}/${{tiles.length}}), showing ${{merged.features.length}}`;
              }}
            }}
            if (myToken !== apiRequestToken) return;
            setCachedResponse(fullKey, merged, bounds, zoom);
            paint(merged, false);
          }} catch (error) {{
            if (error.name === "AbortError") return;
            loadingEl.textContent = "Map request failed";
            console.error(error);
          }}
        }}

        function getStorage() {{
          try {{
            if (window.parent && window.parent.localStorage) {{
              return window.parent.localStorage;
            }}
          }} catch (error) {{
            console.error(error);
          }}
          try {{
            return window.localStorage;
          }} catch (error) {{
            console.error(error);
          }}
          return null;
        }}

        function saveViewState() {{
          const center = map.getCenter();
          const payload = {{
            center: [center.lat, center.lng],
            zoom: map.getZoom()
          }};
          const storage = getStorage();
          if (storage) {{
            storage.setItem(storageKey, JSON.stringify(payload));
          }}
        }}

        function recenterToTarget() {{
          const targetBounds = focus && focus.bounds ? focus.bounds : defaultBounds;
          map.fitBounds(targetBounds, {{ padding: [16, 16], animate: false }});
          saveViewState();
          if (apiBaseUrl) {{
            refreshFromApi();
          }} else {{
            paint(geojson, true);
          }}
        }}

        map.on("moveend", () => {{
          saveViewState();
          if (apiBaseUrl) scheduleRefreshFromApi();
        }});

        map.on("zoomend", () => {{
          saveViewState();
          if (apiBaseUrl) scheduleRefreshFromApi();
          else paint(geojson, true);
        }});

        recenterBtn.addEventListener("click", recenterToTarget);

        const storage = getStorage();
        const savedViewRaw = storage ? storage.getItem(storageKey) : null;
        let restored = false;
        if (!state.should_refocus && savedViewRaw) {{
          try {{
            const savedView = JSON.parse(savedViewRaw);
            if (savedView && savedView.center && typeof savedView.zoom === "number") {{
              map.setView(savedView.center, savedView.zoom, {{ animate: false }});
              restored = true;
            }}
          }} catch (error) {{
            console.error(error);
          }}
        }}

        if (!restored && state.should_refocus && focus && focus.bounds) {{
          map.fitBounds(focus.bounds, {{padding: [16,16], animate: false}});
          saveViewState();
        }} else if (!restored && focus && focus.bounds) {{
          map.fitBounds(focus.bounds, {{padding: [16,16], animate: false}});
          saveViewState();
        }} else if (!restored && !focus) {{
          map.fitBounds(defaultBounds, {{padding: [16,16], animate: false}});
          saveViewState();
        }}

        if (apiBaseUrl) {{
          refreshFromApi();
        }} else {{
          paint(geojson, false);
        }}
      </script>
    </body>
    </html>
    """

    components.html(html, height=height + 6)
