from __future__ import annotations

import json
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from components.shared import render_app_frame, render_metric_cards
from models.external_market import (
    customer_segment_metric,
    load_competitor_store_locations,
    load_customer_segments,
    load_external_source_manifest,
    load_market_demand_frame,
    load_power_tool_authorised_locations,
    load_power_tool_distribution_proxy,
    load_power_tool_manufacturer_competitors,
)
from models.store_locations import load_hilti_store_locations


THREAT_BAND_ORDER = [
    "0-2 km direct local threat",
    "2-5 km strong urban overlap",
    "5-10 km metro overlap",
    "10-25 km regional catchment",
    "25+ km lower direct store threat",
]
PRIORITY_ORDER = ["Very high", "High", "Medium", "Emerging", "Unclassified"]
SEGMENT_OPTIONS = [
    "Total construction demand",
    "Building contractors",
    "Civil engineering",
    "Specialist trades / MEP",
]
THREAT_COLORS = {
    "0-2 km direct local threat": "#c8102e",
    "2-5 km strong urban overlap": "#ef4444",
    "5-10 km metro overlap": "#f97316",
    "10-25 km regional catchment": "#facc15",
    "25+ km lower direct store threat": "#64748b",
}
COMPETITOR_GROUPS = {
    "Core trade counters": ["Screwfix", "Toolstation"],
    "Builders merchants": [
        "Travis Perkins",
        "Jewson",
        "Selco Builders Warehouse",
        "Huws Gray",
        "MKM Building Supplies",
        "Buildbase",
        "B&Q TradePoint",
    ],
    "MEP and electrical trade": ["Wolseley", "City Plumbing", "CEF", "YESSS Electrical", "Edmundson Electrical"],
}
RADIUS_BANDS = {
    "5 km local pressure": THREAT_BAND_ORDER[:2],
    "10 km metro pressure": THREAT_BAND_ORDER[:3],
    "25 km catchment pressure": THREAT_BAND_ORDER[:4],
    "All mapped competitors": THREAT_BAND_ORDER,
}
ANALYSIS_MODES = [
    "Integration Summary",
    "Branch Evidence",
    "Demand Evidence",
    "Manufacturer Evidence",
    "Sources",
]


def _display_name(value: object) -> str:
    text = str(value)
    return text.replace("Hilti Store ", "Construction Hub ")


def _display_all_hubs_label() -> str:
    return "All construction hubs"


def _render_mode_selector() -> str:
    with st.sidebar:
        st.markdown("### Evidence View")
        return st.radio(
            "Choose view",
            options=ANALYSIS_MODES,
            label_visibility="collapsed",
            key="external_market_mode",
            help="Use this page to decide which external signals are worth moving into the Overview dashboard.",
        )


def _filter_stores(stores: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    with st.sidebar:
        st.markdown("### Branch Pressure")

        hub_options = [_display_all_hubs_label()] + sorted(stores["nearest_hilti_store"].dropna().unique().tolist())
        default_hub = st.session_state.get("external_hilti_store", _display_all_hubs_label())
        hub_index = hub_options.index(default_hub) if default_hub in hub_options else 0
        selected_hub = st.selectbox(
            "Construction hub",
            options=hub_options,
            index=hub_index,
            format_func=lambda option: _display_name(option) if option != _display_all_hubs_label() else option,
            help="Review all catchments or focus on one construction hub.",
        )

        competitor_group = st.radio(
            "Competitor group",
            options=["All branch competitors"] + list(COMPETITOR_GROUPS.keys()),
            help="Keep the view focused on the kind of pressure you want to inspect.",
        )

        radius_label = st.radio(
            "Pressure radius",
            options=list(RADIUS_BANDS.keys()),
            index=1,
            help="Show competitors within the selected distance from their nearest construction hub.",
        )

    filtered = stores.copy()
    selected_bands = RADIUS_BANDS[radius_label]
    selected_competitors = COMPETITOR_GROUPS.get(competitor_group)
    if selected_competitors:
        filtered = filtered.loc[filtered["competitor"].isin(selected_competitors)]
    if selected_bands:
        filtered = filtered.loc[filtered["threat_band"].isin(selected_bands)]
    if selected_hub != _display_all_hubs_label():
        filtered = filtered.loc[filtered["nearest_hilti_store"] == selected_hub]

    return filtered, {
        "selected_hilti": selected_hub,
        "competitor_group": competitor_group,
        "radius_label": radius_label,
    }


def _render_customer_controls() -> dict[str, str]:
    with st.sidebar:
        st.markdown("### Customer Demand")
        selected_segment = st.selectbox(
            "Customer segment",
            options=SEGMENT_OPTIONS,
            help="Choose which construction customer proxy to rank.",
        )
    return {"segment": selected_segment}


def _render_manufacturer_controls() -> list[str]:
    manufacturers = load_power_tool_manufacturer_competitors()
    with st.sidebar:
        st.markdown("### Manufacturer Competitors")
        return st.multiselect(
            "Brands",
            options=manufacturers["brand"].tolist(),
            default=manufacturers["brand"].tolist(),
            help="DEWALT and Makita have extracted official locations. Milwaukee and Bosch are status/proxy only.",
        )


def _render_leaflet_point_map(
    points: pd.DataFrame,
    *,
    color_column: str,
    color_map: dict[str, str],
    height: int,
    popup_fields: list[tuple[str, str]],
) -> None:
    if points.empty:
        st.info("No mapped locations match the current filters.")
        return

    map_id = f"external_map_{uuid4().hex}"
    hilti_stores = load_hilti_store_locations().to_dict("records")
    payload = []
    for row in points.to_dict("records"):
        lat = row.get("latitude")
        lon = row.get("longitude")
        if pd.isna(lat) or pd.isna(lon):
            continue
        payload.append(row)

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
          border-radius: 14px;
          overflow: hidden;
        }}
        .hilti-marker {{
          width: 22px;
          height: 22px;
          border-radius: 999px;
          background: #c8102e;
          color: #fff;
          border: 2px solid #fff;
          box-shadow: 0 8px 18px rgba(15,23,42,0.24);
          display: flex;
          align-items: center;
          justify-content: center;
          font: 11px/1 sans-serif;
          font-weight: 700;
        }}
        .legend {{
          background: rgba(255,255,255,0.96);
          padding: 10px 12px;
          border-radius: 10px;
          box-shadow: 0 8px 24px rgba(15,23,42,0.16);
          font: 12px/1.35 sans-serif;
        }}
        .legend-row {{
          display: flex;
          align-items: center;
          gap: 7px;
          margin-top: 5px;
        }}
        .legend-dot {{
          width: 10px;
          height: 10px;
          border-radius: 999px;
          border: 1px solid rgba(16,24,40,0.18);
        }}
      </style>
    </head>
    <body>
      <div id="{map_id}"></div>
      <script>
        const points = {json.dumps(payload, default=str)};
        const constructionStores = {json.dumps(hilti_stores, default=str)};
        const colorColumn = {json.dumps(color_column)};
        const colorMap = {json.dumps(color_map)};
        const popupFields = {json.dumps(popup_fields)};
        const map = L.map("{map_id}", {{
          center: [54.5, -3.0],
          zoom: 6,
          zoomControl: true,
          scrollWheelZoom: true,
          preferCanvas: true
        }});
        L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        const bounds = [];
        points.forEach((point) => {{
          const lat = Number(point.latitude);
          const lon = Number(point.longitude);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
          const color = colorMap[point[colorColumn]] || "#64748b";
          const marker = L.circleMarker([lat, lon], {{
            radius: 6,
            color: "#ffffff",
            weight: 1,
            fillColor: color,
            fillOpacity: 0.84
          }});
          const title = point.store_name || point.location_name || point.competitor || point.brand || "Location";
          const rows = popupFields.map(([label, key]) => {{
            const value = point[key];
            if (value === undefined || value === null || value === "" || Number.isNaN(value)) return "";
            return `<div><strong>${{label}}:</strong> ${{value}}</div>`;
          }}).join("");
          marker.bindPopup(`<strong>${{title}}</strong>${{rows}}`);
          marker.addTo(map);
          bounds.push([lat, lon]);
        }});

        constructionStores.forEach((store) => {{
          const lat = Number(store.latitude);
          const lon = Number(store.longitude);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
          const icon = L.divIcon({{
            className: "",
            html: '<div class="hilti-marker">C</div>',
            iconSize: [22, 22],
            iconAnchor: [11, 11]
          }});
          L.marker([lat, lon], {{ icon }}).bindPopup(`<strong>${{store.name}}</strong><div>${{store.postcode || ""}}</div>`).addTo(map);
          bounds.push([lat, lon]);
        }});

        if (bounds.length > 0) {{
          map.fitBounds(bounds, {{ padding: [28, 28], maxZoom: 11 }});
        }}

        const legend = L.control({{ position: "bottomright" }});
        legend.onAdd = function() {{
          const div = L.DomUtil.create("div", "legend");
          const rows = Object.entries(colorMap).map(([label, color]) =>
            `<div class="legend-row"><span class="legend-dot" style="background:${{color}}"></span><span>${{label}}</span></div>`
          ).join("");
          div.innerHTML = `<strong>Legend</strong>${{rows}}<div class="legend-row"><span class="legend-dot" style="background:#c8102e"></span><span>Construction hub</span></div>`;
          return div;
        }};
        legend.addTo(map);
      </script>
    </body>
    </html>
    """
    components.html(html, height=height, scrolling=False)


def _render_competitor_map(filtered: pd.DataFrame) -> None:
    map_frame = filtered.sort_values("distance_to_nearest_hilti_km").head(1600).copy()
    if map_frame.empty:
        st.info("No competitor branches match the current filters.")
        return

    _render_leaflet_point_map(
        map_frame,
        color_column="threat_band",
        color_map=THREAT_COLORS,
        height=620,
        popup_fields=[
            ("Competitor", "competitor"),
            ("Priority", "priority"),
            ("Nearest hub", "nearest_hilti_store"),
            ("Distance km", "distance_to_nearest_hilti_km"),
            ("Postcode", "postcode"),
        ],
    )


def _branch_pressure_summary(filtered: pd.DataFrame) -> pd.DataFrame:
    threat_summary = (
        filtered.groupby(["nearest_hilti_store", "threat_band"], observed=True)
        .size()
        .reset_index(name="competitor_branches")
    )
    pivot = threat_summary.pivot_table(
        index="nearest_hilti_store",
        columns="threat_band",
        values="competitor_branches",
        fill_value=0,
        aggfunc="sum",
    ).reset_index()
    for band in THREAT_BAND_ORDER:
        if band not in pivot.columns:
            pivot[band] = 0
    pivot["0-10 km total"] = pivot[THREAT_BAND_ORDER[:3]].sum(axis=1)
    pivot["0-25 km total"] = pivot[THREAT_BAND_ORDER[:4]].sum(axis=1)
    return pivot.sort_values(["0-10 km total", "0-25 km total"], ascending=False)


def _render_competitor_tables(filtered: pd.DataFrame) -> None:
    pivot = _branch_pressure_summary(filtered)
    nearest = filtered.sort_values("distance_to_nearest_hilti_km").head(25).loc[
        :,
        [
            "competitor",
            "store_name",
            "nearest_hilti_store",
            "distance_to_nearest_hilti_km",
            "threat_band",
            "postcode",
            "city",
        ],
    ]

    left, right = st.columns([1.15, 0.85], gap="medium")
    with left:
        st.subheader("Which Construction Hubs Are Most Exposed?")
        st.caption("Competitor branches are assigned to their nearest construction hub.")
        st.dataframe(pivot, width="stretch", hide_index=True)
    with right:
        st.subheader("Closest Competitor Branches")
        st.caption("Branches most likely to create direct local convenience pressure.")
        st.dataframe(nearest, width="stretch", hide_index=True)


def _render_executive_takeaway(filtered: pd.DataFrame, controls: dict[str, object]) -> None:
    if filtered.empty:
        st.info("No competitor branches match this view. Broaden the radius or switch competitor group.")
        return

    summary = _branch_pressure_summary(filtered)
    top_store = summary.iloc[0]["nearest_hilti_store"] if not summary.empty else "N/A"
    top_count = int(summary.iloc[0]["0-10 km total"]) if not summary.empty else 0
    closest = filtered.sort_values("distance_to_nearest_hilti_km").iloc[0]

    st.markdown(
        f"""
        **Read this view as a pressure check.** For **{controls["competitor_group"]}** inside **{controls["radius_label"]}**, the most exposed construction hub is **{top_store}** with **{top_count}** mapped competitor branches within 10 km. The nearest mapped branch is **{closest["store_name"]}** ({closest["competitor"]}) at **{closest["distance_to_nearest_hilti_km"]:.1f} km** from **{closest["nearest_hilti_store"]}**.
        """
    )


def _render_customer_proxy(segment: str) -> None:
    demand = load_market_demand_frame()
    metric, metric_label = customer_segment_metric(segment)
    ranking = demand.sort_values(metric, ascending=False).head(20).copy()
    ranking["population_mid_2024"] = ranking["population_mid_2024"].round(0).astype("Int64")
    ranking["construction_units_per_10k_people"] = ranking["construction_units_per_10k_people"].round(1)

    st.subheader("Customer Demand Proxy")
    st.caption(
        f"Ranking local authorities by {metric_label}. Source: Nomis UK Business Counts local units, joined to ONS mid-2024 population."
    )

    fig = px.scatter(
        demand,
        x="population_mid_2024",
        y=metric,
        size="construction_customer_proxy_local_units_total",
        color="geography_type",
        hover_name="area_name",
        hover_data={
            "area_code": True,
            "construction_customer_proxy_local_units_total": ":,.0f",
            "construction_units_per_10k_people": ":.1f",
        },
        labels={
            "population_mid_2024": "Population mid-2024",
            metric: metric_label,
            "geography_type": "Geography",
        },
        height=420,
    )
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    table = ranking.loc[
        :,
        [
            "area_name",
            "area_code",
            "population_mid_2024",
            "construction_buildings_local_units",
            "civil_engineering_local_units",
            "specialised_construction_local_units",
            "construction_customer_proxy_local_units_total",
            "construction_units_per_10k_people",
        ],
    ]
    table.columns = [
        "Area",
        "Area code",
        "Population",
        "SIC 41 buildings",
        "SIC 42 civil engineering",
        "SIC 43 specialist trades",
        "Total construction units",
        "Units per 10k people",
    ]
    st.dataframe(table, width="stretch", hide_index=True)


def _render_customer_segments() -> None:
    with st.expander("Customer segment research used by this page", expanded=False):
        st.dataframe(load_customer_segments(), width="stretch", hide_index=True)


def _integration_evidence() -> pd.DataFrame:
    stores = load_competitor_store_locations()
    demand = load_market_demand_frame()
    manufacturers = load_power_tool_manufacturer_competitors()
    manufacturer_locations = load_power_tool_authorised_locations()
    pressure_10km = stores.loc[stores["threat_band"].isin(THREAT_BAND_ORDER[:3])]
    pressure_summary = _branch_pressure_summary(pressure_10km)
    top_pressure = pressure_summary.iloc[0] if not pressure_summary.empty else None
    top_demand = demand.sort_values("construction_customer_proxy_local_units_total", ascending=False).iloc[0]

    return pd.DataFrame(
        [
            {
                "Signal": "Competitor branch pressure",
                "Evidence": f"{len(stores):,} mapped competitor branches; top 10km pressure is {int(top_pressure['0-10 km total']) if top_pressure is not None else 0} near {top_pressure['nearest_hilti_store'] if top_pressure is not None else 'N/A'}",
                "Overview value": "High. Gives managers immediate context on where construction hubs face local convenience pressure.",
                "Decision": "Integrate as optional pressure badge and detail panel",
            },
            {
                "Signal": "Construction customer demand",
                "Evidence": f"{len(demand):,} local authority areas; {int(demand['construction_customer_proxy_local_units_total'].sum()):,} construction local units; top area is {top_demand['area_name']}",
                "Overview value": "High. Helps separate areas with real customer density from areas with pressure but limited demand.",
                "Decision": "Integrate as market demand context, not as a raw map layer",
            },
            {
                "Signal": "Power-tool manufacturer competitors",
                "Evidence": f"{len(manufacturers):,} brands researched; {len(manufacturer_locations):,} official DEWALT/Makita locations extracted",
                "Overview value": "Medium. Useful for narrative and product-system threat, but not directly comparable with construction hubs.",
                "Decision": "Keep in drill-down or methodology, do not add to main Overview yet",
            },
            {
                "Signal": "Population",
                "Evidence": f"{int(demand['population_mid_2024'].sum()):,} people covered across local authority rows",
                "Overview value": "Medium. Useful as a denominator, but population alone is weak for construction demand.",
                "Decision": "Use only to normalise construction demand",
            },
        ]
    )


def _render_integration_summary() -> None:
    evidence = _integration_evidence()
    stores = load_competitor_store_locations()
    demand = load_market_demand_frame()
    pressure_10km = stores.loc[stores["threat_band"].isin(THREAT_BAND_ORDER[:3])]
    pressure_summary = _branch_pressure_summary(pressure_10km)
    top_pressure = pressure_summary.iloc[0]
    top_demand = demand.sort_values("construction_customer_proxy_local_units_total", ascending=False).iloc[0]

    render_metric_cards(
        [
            ("Recommendation", "Pilot", "Integrate two external signals first"),
            ("Best pressure signal", f"{int(top_pressure['0-10 km total'])}", f"Competitors within 10 km of {top_pressure['nearest_hilti_store']}"),
            ("Best demand signal", f"{int(top_demand['construction_customer_proxy_local_units_total']):,}", f"Construction units in {top_demand['area_name']}"),
            ("Signals to defer", "Manufacturer layer", "Keep as drill-down evidence for now"),
        ]
    )

    with st.container(border=True):
        st.subheader("Should This Go Into Overview?")
        st.markdown(
            """
            **Yes, but only as a compact pressure-and-demand panel.** The external data is useful, but it should not take over the Overview page. The strongest implementation would add two small context signals beside the existing territory story:

            - **Competitor pressure within 10 km** of the relevant construction hub.
            - **Construction customer demand** from Nomis local-unit counts.

            Manufacturer competitor data should stay in this page for now because DEWALT/Makita official points are service/dealer networks, while Milwaukee/Bosch only have researched locator/proxy coverage.
            """
        )

    with st.container(border=True):
        st.subheader("Evidence Matrix")
        st.dataframe(evidence, width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Recommended Overview Integration")
        proposed = pd.DataFrame(
            [
                {
                    "Overview element": "External pressure badge",
                    "Data source": "Competitor branches within 10 km",
                    "User value": "Shows whether the selected construction hub is crowded by trade counters.",
                },
                {
                    "Overview element": "Demand context line",
                    "Data source": "Nomis SIC 41/42/43 construction local units",
                    "User value": "Shows whether pressure is worth acting on because customer density exists.",
                },
                {
                    "Overview element": "Drill-down link",
                    "Data source": "This external page",
                    "User value": "Keeps Overview clean while allowing evidence inspection.",
                },
            ]
        )
        st.dataframe(proposed, width="stretch", hide_index=True)


def _render_power_tool_manufacturers(selected_brands: list[str]) -> None:
    manufacturers = load_power_tool_manufacturer_competitors()
    locations = load_power_tool_authorised_locations()
    proxy = load_power_tool_distribution_proxy()

    st.subheader("Power-Tool Manufacturer Competitors")
    st.caption(
        "DEWALT and Makita include official locator coordinates where extractable. Milwaukee Tool and Bosch Professional are represented as researched manufacturer threats with official locator links and distribution proxies."
    )

    selected_locations = locations.loc[locations["brand"].isin(selected_brands)].copy()

    top, bottom = st.columns([1.55, 0.95], gap="medium")
    with top:
        if selected_locations.empty:
            st.info("No extracted official coordinate layer is available for the selected manufacturer brands.")
        else:
            _render_leaflet_point_map(
                selected_locations.sort_values("distance_to_nearest_hilti_km").head(1500),
                color_column="brand",
                color_map={
                    "DEWALT": "#111827",
                    "Makita": "#0099a8",
                    "Milwaukee Tool": "#c8102e",
                    "Bosch Professional": "#1d4ed8",
                },
                height=500,
                popup_fields=[
                    ("Brand", "brand"),
                    ("Type", "location_type"),
                    ("Nearest hub", "nearest_hilti_store"),
                    ("Distance km", "distance_to_nearest_hilti_km"),
                    ("Postcode", "postcode"),
                    ("Services", "services"),
                ],
            )

    with bottom:
        status = manufacturers.loc[
            manufacturers["brand"].isin(selected_brands),
            ["brand", "manufacturer", "uk_location_status", "official_locator_url"],
        ].copy()
        st.write("**Research Status**")
        st.dataframe(status, width="stretch", hide_index=True)

    if not selected_locations.empty:
        summary = (
            selected_locations.groupby(["brand", "nearest_hilti_store"], observed=True)
            .size()
            .reset_index(name="authorised_locations")
            .sort_values(["brand", "authorised_locations"], ascending=[True, False])
        )
        closest = selected_locations.sort_values("distance_to_nearest_hilti_km").head(30).loc[
            :,
            [
                "brand",
                "location_name",
                "location_type",
                "nearest_hilti_store",
                "distance_to_nearest_hilti_km",
                "postcode",
            ],
        ]
        left, right = st.columns([1.0, 1.1], gap="medium")
        with left:
            st.write("**Official Locations by Nearest Construction Hub**")
            st.dataframe(summary, width="stretch", hide_index=True)
        with right:
            st.write("**Closest Manufacturer Authorised Locations**")
            st.dataframe(closest, width="stretch", hide_index=True)

    with st.expander("Distribution proxy through already mapped branch networks", expanded=False):
        st.caption(
            "These are not manufacturer-owned stores. They indicate where the brand threat can be proxied through mapped trade-counter or merchant networks."
        )
        st.dataframe(proxy.loc[proxy["brand"].isin(selected_brands)], width="stretch", hide_index=True)


def render_page() -> None:
    stores = load_competitor_store_locations()
    manifest = load_external_source_manifest()

    render_app_frame(
        title="External Data Integration Check",
        subtitle="A compact evidence page for deciding what, if anything, should be carried into the Overview dashboard.",
    )

    mode = _render_mode_selector()

    if mode == "Branch Evidence":
        filtered, controls = _filter_stores(stores)
    else:
        filtered = stores.copy()
        controls = {
            "selected_hilti": _display_all_hubs_label(),
            "competitor_group": "All branch competitors",
            "radius_label": "All mapped competitors",
        }

    if mode == "Integration Summary":
        _render_integration_summary()

    elif mode == "Branch Evidence":
        direct_threats = int(filtered["threat_band"].isin(THREAT_BAND_ORDER[:2]).sum())
        closest = filtered["distance_to_nearest_hilti_km"].min()
        closest_text = f"{closest:.1f} km" if pd.notna(closest) else "N/A"
        competitor_count = filtered["competitor"].nunique()
        hilti_count = filtered["nearest_hilti_store"].nunique()

        render_metric_cards(
            [
                ("Competitor branches", f"{len(filtered):,}", "Filtered OSM branch points"),
                ("Competitor chains", f"{competitor_count}", str(controls["competitor_group"])),
                ("Direct local threats", f"{direct_threats:,}", "Branches within 5 km of nearest hub"),
                ("Closest overlap", closest_text, f"Across {hilti_count} construction hub catchments"),
            ]
        )

        with st.container(border=True):
            _render_executive_takeaway(filtered, controls)

        left, right = st.columns([1.55, 0.8], gap="medium")
        with left:
            with st.container(border=True):
                st.subheader("Nearby Competitor Branches")
                st.caption("Point color shows how close each competitor branch is to its nearest construction hub.")
                _render_competitor_map(filtered)
        with right:
            with st.container(border=True):
                st.subheader("Competitor Mix")
                mix = (
                    filtered.groupby(["competitor", "priority"], observed=True)
                    .size()
                    .reset_index(name="branches")
                    .sort_values("branches", ascending=False)
                    .head(15)
                )
                if mix.empty:
                    st.info("No competitor mix to show for the current filters.")
                else:
                    st.dataframe(mix, width="stretch", hide_index=True)

        st.markdown('<div style="height:0.6rem;"></div>', unsafe_allow_html=True)
        _render_competitor_tables(filtered)

    elif mode == "Demand Evidence":
        demand_controls = _render_customer_controls()
        demand = load_market_demand_frame()
        metric, metric_label = customer_segment_metric(str(demand_controls["segment"]))
        top_area = demand.sort_values(metric, ascending=False).iloc[0]
        render_metric_cards(
            [
                ("Local authority areas", f"{len(demand):,}", "ONS and Nomis joined areas"),
                ("Construction local units", f"{int(demand['construction_customer_proxy_local_units_total'].sum()):,}", "SIC 41, 42 and 43 total"),
                ("Top demand area", str(top_area["area_name"]), metric_label),
                ("Population covered", f"{int(demand['population_mid_2024'].sum()):,}", "Mid-2024 local authority population"),
            ]
        )
        with st.container(border=True):
            _render_customer_proxy(str(demand_controls["segment"]))

    elif mode == "Manufacturer Evidence":
        selected_brands = _render_manufacturer_controls()
        locations = load_power_tool_authorised_locations()
        selected_locations = locations.loc[locations["brand"].isin(selected_brands)]
        extracted_brands = selected_locations["brand"].nunique()
        render_metric_cards(
            [
                ("Manufacturer brands", f"{len(selected_brands):,}", "Selected product-system competitors"),
                ("Official locations", f"{len(selected_locations):,}", "Extracted DEWALT and Makita points"),
                ("Mapped brands", f"{extracted_brands}", "Brands with coordinate coverage"),
                ("Proxy links", f"{len(load_power_tool_distribution_proxy()):,}", "Retailer and merchant distribution proxies"),
            ]
        )
        with st.container(border=True):
            _render_power_tool_manufacturers(selected_brands)

    else:
        row_counts = manifest.get("row_counts", {})
        render_metric_cards(
            [
                ("Competitor points", f"{row_counts.get('competitor_store_locations_osm', len(stores)):,}", "OSM branch layer"),
                ("Demand areas", f"{row_counts.get('population_local_authority_mid2024', 0):,}", "ONS local-authority population"),
                ("Construction rows", f"{row_counts.get('customer_proxy_construction_rows', 0):,}", "Nomis SIC rows"),
                ("Manufacturer locations", f"{row_counts.get('power_tool_authorised_locations', 0):,}", "DEWALT and Makita official points"),
            ]
        )
        with st.container(border=True):
            st.subheader("What Data Is Driving This View?")
            source_rows = [
                ("Competitor branch points", row_counts.get("competitor_store_locations_osm", len(stores))),
                ("Population local-authority rows", row_counts.get("population_local_authority_mid2024", 0)),
                ("Construction proxy rows", row_counts.get("customer_proxy_construction_rows", 0)),
                ("Power-tool authorised locations", row_counts.get("power_tool_authorised_locations", 0)),
            ]
            st.dataframe(pd.DataFrame(source_rows, columns=["Dataset", "Rows"]), width="stretch", hide_index=True)
            st.caption("Full source links and limitations are documented in the external research report.")

        _render_customer_segments()
