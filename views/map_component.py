from __future__ import annotations

import json
from uuid import uuid4

import streamlit.components.v1 as components


def render_leaflet_metric_map(
    server_url: str,
    filters: dict[str, object],
    metric_key: str,
    metric_label: str,
    focus_record: dict[str, object] | None,
    should_refocus: bool,
    store_locations: list[dict[str, object]] | None = None,
    focus_district: str | None = None,
    weights: dict[str, float] | None = None,
    active_keys: list[str] | None = None,
    height: int = 720,
) -> None:
    map_id = f"map_{uuid4().hex}"
    state = {
        **filters,
        "metric_key": metric_key,
        "metric_label": metric_label,
        "should_refocus": should_refocus,
        "focus_district": focus_district,
        "store_locations": store_locations or [],
        "weights": weights or {},
        "active_keys": active_keys or [],
    }

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
        const serverUrl = {json.dumps(server_url)};
        const storeLocations = state.store_locations || [];
        const loadingEl = document.getElementById("loading");
        const recenterBtn = document.getElementById("recenterBtn");
        const responseCache = new Map();
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
          const value = p[state.metric_key];
          if (value === null || value === undefined) {{
            return {{
              color: "#98a2b3",
              weight: 0.75,
              fillColor: "#d0d5dd",
              fillOpacity: 0.12
            }};
          }}

          const highlightedDistrict = state.focus_district || state.district;
          const isFocus = highlightedDistrict && highlightedDistrict !== "All" && p.post_dist === highlightedDistrict;
          return {{
            color: isFocus ? "#101828" : "#4b2e17",
            weight: isFocus ? 2.0 : 0.8,
            fillColor: colorForMetric(value),
            fillOpacity: isFocus ? 0.74 : 0.58
          }};
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

        function buildQuery() {{
          const bounds = map.getBounds();
          const params = new URLSearchParams();
          params.set("west", bounds.getWest().toFixed(6));
          params.set("south", bounds.getSouth().toFixed(6));
          params.set("east", bounds.getEast().toFixed(6));
          params.set("north", bounds.getNorth().toFixed(6));
          params.set("zoom", String(map.getZoom()));

          if (state.post_area && state.post_area !== "All") params.set("post_area", state.post_area);
          if (state.sprawl && state.sprawl !== "All") params.set("sprawl", state.sprawl);
          if (state.district && state.district !== "All") params.set("district", state.district);
          if (state.segment && state.segment !== "All") params.set("segment", state.segment);
          if (state.observed_only) params.set("observed_only", "1");

          if (state.active_keys && state.active_keys.length) {{
            params.set("active", state.active_keys.join(","));
          }}
          if (state.weights) {{
            Object.entries(state.weights).forEach(([key, value]) => {{
              params.set(`w_${{key}}`, String(value));
            }});
          }}
          return `${{serverUrl}}/districts?${{params.toString()}}`;
        }}

        async function refresh() {{
          try {{
            const query = buildQuery();
            const cached = responseCache.get(query);
            if (cached) {{
              paint(cached, true);
              return;
            }}

            loadingEl.textContent = "Loading map data…";
            const response = await fetch(query);
            const geojson = await response.json();
            responseCache.set(query, geojson);
            if (responseCache.size > 24) {{
              const firstKey = responseCache.keys().next().value;
              responseCache.delete(firstKey);
            }}
            paint(geojson, false);
          }} catch (error) {{
            loadingEl.textContent = "Map request failed";
            console.error(error);
          }}
        }}

        function paint(geojson, fromCache) {{
            districtLayer.clearLayers();
            markerLayer.clearLayers();
            storeLayer.clearLayers();
            districtLayer.addData(geojson);

            if (geojson.features) {{
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
            loadingEl.textContent = (fromCache ? "Loaded from cache: " : "Loaded ") + count + " district polygons";
        }}

        let timer = null;
        function queueRefresh() {{
          if (timer) clearTimeout(timer);
          timer = setTimeout(refresh, 140);
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
          queueRefresh();
        }}

        map.on("moveend zoomend", () => {{
          saveViewState();
          queueRefresh();
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

        queueRefresh();
      </script>
    </body>
    </html>
    """

    components.html(html, height=height + 6)
