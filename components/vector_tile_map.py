"""MapLibre GL + MVT for API-backed maps (lighter than one giant GeoJSON)."""

from __future__ import annotations

import html as html_module
import json
from urllib.parse import urlencode
from uuid import uuid4

import streamlit.components.v1 as components


def _tile_query_string(
    filters: dict[str, object] | None,
    weights: dict[str, float] | None,
    active_keys: list[str] | None,
) -> str:
    f = filters or {}
    w = weights or {}
    active = active_keys or []
    pairs = [
        ("sprawl", str(f.get("sprawl", "All"))),
        ("district", str(f.get("district", "All"))),
        ("segment", str(f.get("segment", "All"))),
        ("active", ",".join(active)),
    ]
    for key, val in w.items():
        pairs.append((f"w_{key}", str(float(val))))
    return urlencode(pairs)


def render_vector_tile_map(
    api_base_url: str,
    metric_key: str,
    metric_label: str,
    focus_record: dict[str, object] | None,
    should_refocus: bool,
    filters: dict[str, object] | None,
    store_locations: list[dict[str, object]] | None,
    focus_district: str | None,
    weights: dict[str, float] | None,
    active_keys: list[str] | None,
    height: int = 720,
) -> None:
    map_id = f"vlmap_{uuid4().hex}"
    state = {
        **(filters or {}),
        "metric_key": metric_key,
        "metric_label": metric_label,
        "should_refocus": should_refocus,
        "focus_district": focus_district or "",
        "store_locations": store_locations or [],
    }
    tile_qs = _tile_query_string(filters, weights, active_keys)
    focus = focus_record

    map_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
      <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
      <style>
        html, body, #{map_id} {{
          width: 100%; height: {height}px; margin: 0; padding: 0;
          border-radius: 18px; overflow: hidden;
        }}
        .wrap {{
          position: relative; width: 100%; height: {height}px;
          border-radius: 18px; border: 1px solid rgba(16,24,40,0.08); overflow: hidden;
        }}
        .loading {{
          position: absolute; right: 12px; top: 12px; z-index: 2;
          background: rgba(255,255,255,0.96); border-radius: 12px; padding: 7px 10px;
          font: 12px/1.3 sans-serif; color: #344054;
        }}
        .legend {{
          position: absolute; right: 12px; bottom: 12px; z-index: 2;
          background: rgba(255,255,255,0.96); padding: 10px 12px; border-radius: 12px;
          font: 12px/1.4 sans-serif; box-shadow: 0 8px 24px rgba(15,23,42,0.18);
        }}
        .legend-scale {{
          width: 160px; height: 10px; border-radius: 999px;
          background: linear-gradient(90deg, #ea4335 0%, #fbbc04 50%, #34a853 100%);
          margin: 8px 0 4px 0;
        }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div id="loading" class="loading">Loading vector map…</div>
        <div class="legend">
          <div><strong>{html_module.escape(metric_label)}</strong></div>
          <div class="legend-scale"></div>
          <div style="display:flex;justify-content:space-between;"><span>Low</span><span>High</span></div>
        </div>
        <div id="{map_id}"></div>
      </div>
      <script>
        const state = {json.dumps(state)};
        const focus = {json.dumps(focus)};
        const apiBase = {json.dumps(api_base_url.rstrip("/"))};
        const tileQs = {json.dumps(tile_qs)};
        const metricKey = {json.dumps(metric_key)};
        const stores = state.store_locations || [];
        const loadingEl = document.getElementById("loading");

        const defaultBounds = [[-8.2, 49.8], [2.2, 60.9]];

        function focusLngLatBounds() {{
          if (!focus || !focus.bounds) return null;
          const b = focus.bounds;
          return [[b[0][1], b[0][0]], [b[1][1], b[1][0]]];
        }}

        const map = new maplibregl.Map({{
          container: "{map_id}",
          style: {{
            version: 8,
            sources: {{
              osm: {{
                type: "raster",
                tiles: ["https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png"],
                tileSize: 256,
                attribution: "&copy; OpenStreetMap"
              }}
            }},
            layers: [{{ id: "bg", type: "raster", source: "osm" }}]
          }},
          center: [-3, 54.5],
          zoom: 5.5,
          maxBounds: [[-12, 49], [4, 61]]
        }});

        map.on("load", () => {{
          const tileUrl = apiBase + "/tiles/{{z}}/{{x}}/{{y}}.mvt?" + tileQs;
          map.addSource("districts", {{
            type: "vector",
            tiles: [tileUrl],
            scheme: "xyz",
            minzoom: 4,
            maxzoom: 14
          }});

          const fillColor = [
            "interpolate", ["linear"], ["coalesce", ["get", metricKey], 0],
            0, "#ea4335",
            50, "#fbbc04",
            100, "#34a853"
          ];

          const fd = state.focus_district && state.focus_district !== "All" ? state.focus_district : "";

          map.addLayer({{
            id: "district-fill",
            type: "fill",
            source: "districts",
            "source-layer": "districts",
            paint: {{
              "fill-color": fillColor,
              "fill-opacity": fd ? [
                "case", ["==", ["get", "post_dist"], fd], 0.78, 0.52
              ] : 0.55,
              "fill-outline-color": "#4b2e17"
            }}
          }});

          stores.forEach((store) => {{
            if (!store.latitude || !store.longitude) return;
            const el = document.createElement("div");
            el.style.cssText = "width:22px;height:22px;border-radius:999px;background:#c8102e;color:#fff;border:2px solid #fff;display:flex;align-items:center;justify-content:center;font:11px/1 sans-serif;font-weight:700;";
            el.textContent = "H";
            new maplibregl.Marker({{ element: el }})
              .setLngLat([store.longitude, store.latitude])
              .setPopup(new maplibregl.Popup({{ offset: 12 }}).setHTML(
                "<div style='min-width:180px'><b>" + (store.name || "") + "</b><br/>City: " + (store.city || "") + "</div>"
              ))
              .addTo(map);
          }});

          const fb = focusLngLatBounds();
          if (state.should_refocus && fb) {{
            map.fitBounds(fb, {{ padding: 40, maxZoom: 11, duration: 0 }});
          }} else if (fb) {{
            map.fitBounds(fb, {{ padding: 40, maxZoom: 11, duration: 0 }});
          }} else {{
            map.fitBounds(defaultBounds, {{ padding: 24, duration: 0 }});
          }}

          loadingEl.textContent = "Vector map ready";
          setTimeout(() => {{ loadingEl.style.display = "none"; }}, 1200);
        }});

        map.on("error", (e) => {{
          loadingEl.textContent = "Map error: " + (e.error && e.error.message ? e.error.message : "unknown");
        }});
      </script>
    </body>
    </html>
    """
    components.html(map_html, height=height + 6)
