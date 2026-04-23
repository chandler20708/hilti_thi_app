from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from components.shared import render_app_frame, render_metric_cards
from models.external_market import (
    customer_segment_metric,
    load_competitor_store_locations,
    load_customer_segments,
    load_external_source_manifest,
    load_market_demand_frame,
)


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


def _default_filter_values(values: list[str], defaults: list[str]) -> list[str]:
    return [value for value in defaults if value in values] or values


def _filter_stores(stores: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    with st.sidebar:
        st.markdown("### External Market")

        priorities = [value for value in PRIORITY_ORDER if value in set(stores["priority"])]
        selected_priorities = st.multiselect(
            "Competitor priority",
            options=priorities,
            default=_default_filter_values(priorities, ["Very high", "High", "Medium"]),
            help="Filter competitor chains by the researched strategic priority.",
        )

        competitor_options = sorted(
            stores.loc[stores["priority"].isin(selected_priorities), "competitor"].dropna().unique().tolist()
            if selected_priorities
            else stores["competitor"].dropna().unique().tolist()
        )
        selected_competitors = st.multiselect(
            "Competitors",
            options=competitor_options,
            default=competitor_options,
            help="Choose which competitor branch networks to show on the map.",
        )

        selected_bands = st.multiselect(
            "Threat distance band",
            options=THREAT_BAND_ORDER,
            default=THREAT_BAND_ORDER[:4],
            help="Distance from the competitor branch to the nearest Hilti store.",
        )

        hilti_options = ["All Hilti stores"] + sorted(stores["nearest_hilti_store"].dropna().unique().tolist())
        selected_hilti = st.selectbox(
            "Nearest Hilti store",
            options=hilti_options,
            help="Focus on competitor branches whose nearest Hilti store is the selected location.",
        )

        selected_segment = st.selectbox(
            "Customer proxy segment",
            options=SEGMENT_OPTIONS,
            help="Switch the customer-demand ranking between construction business segments.",
        )

        max_points = st.slider(
            "Map point limit",
            min_value=250,
            max_value=3000,
            value=1500,
            step=250,
            help="Limit points shown on the browser map while keeping the tables computed from all filtered rows.",
        )

    filtered = stores.copy()
    if selected_priorities:
        filtered = filtered.loc[filtered["priority"].isin(selected_priorities)]
    if selected_competitors:
        filtered = filtered.loc[filtered["competitor"].isin(selected_competitors)]
    if selected_bands:
        filtered = filtered.loc[filtered["threat_band"].isin(selected_bands)]
    if selected_hilti != "All Hilti stores":
        filtered = filtered.loc[filtered["nearest_hilti_store"] == selected_hilti]

    return filtered, {
        "segment": selected_segment,
        "max_points": max_points,
        "selected_hilti": selected_hilti,
    }


def _render_competitor_map(filtered: pd.DataFrame, max_points: int) -> None:
    map_frame = filtered.sort_values("distance_to_nearest_hilti_km").head(max_points).copy()
    if map_frame.empty:
        st.info("No competitor branches match the current filters.")
        return

    fig = px.scatter_mapbox(
        map_frame,
        lat="latitude",
        lon="longitude",
        color="threat_band",
        color_discrete_map=THREAT_COLORS,
        category_orders={"threat_band": THREAT_BAND_ORDER},
        hover_name="store_name",
        hover_data={
            "competitor": True,
            "priority": True,
            "nearest_hilti_store": True,
            "distance_to_nearest_hilti_km": ":.1f",
            "postcode": True,
            "latitude": False,
            "longitude": False,
        },
        zoom=5,
        height=650,
    )
    fig.update_layout(
        mapbox_style="open-street-map",
        margin=dict(l=0, r=0, t=0, b=0),
        legend_title_text="Threat band",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _render_competitor_tables(filtered: pd.DataFrame) -> None:
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
    pivot = pivot.sort_values(["0-10 km total", "0-25 km total"], ascending=False)

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
        st.subheader("Hilti Stores Under Local Branch Pressure")
        st.caption("Counts are based on competitor branches whose nearest Hilti point is the listed store.")
        st.dataframe(pivot, width="stretch", hide_index=True)
    with right:
        st.subheader("Closest Competitor Branches")
        st.caption("Nearest branches in the current filter set.")
        st.dataframe(nearest, width="stretch", hide_index=True)


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


def render_page() -> None:
    stores = load_competitor_store_locations()
    manifest = load_external_source_manifest()

    render_app_frame(
        title="External Market Intelligence",
        subtitle="Overlay competitor branch pressure with construction customer-demand proxies and population context.",
    )

    filtered, controls = _filter_stores(stores)

    direct_threats = int(filtered["threat_band"].isin(THREAT_BAND_ORDER[:2]).sum())
    closest = filtered["distance_to_nearest_hilti_km"].min()
    closest_text = f"{closest:.1f} km" if pd.notna(closest) else "N/A"
    competitor_count = filtered["competitor"].nunique()
    hilti_count = filtered["nearest_hilti_store"].nunique()

    render_metric_cards(
        [
            ("Competitor branches", f"{len(filtered):,}", "Filtered OSM branch points"),
            ("Competitor chains", f"{competitor_count}", "Brands in the current view"),
            ("Direct local threats", f"{direct_threats:,}", "Branches within 5 km of nearest Hilti"),
            ("Closest overlap", closest_text, f"Across {hilti_count} Hilti store catchments"),
        ]
    )

    left, right = st.columns([1.65, 0.75], gap="medium")
    with left:
        with st.container(border=True):
            st.subheader("Competitor Store Threat Map")
            st.caption(
                "Point colors represent distance to the nearest Hilti store. The full CSV also includes latitude, longitude, OSM ID, nearest Hilti, and source URL."
            )
            _render_competitor_map(filtered, int(controls["max_points"]))
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

        with st.container(border=True):
            st.subheader("Source Snapshot")
            row_counts = manifest.get("row_counts", {})
            st.write(f"OSM competitor points: **{row_counts.get('competitor_store_locations_osm', len(stores)):,}**")
            st.write(f"Population LA rows: **{row_counts.get('population_local_authority_mid2024', 0):,}**")
            st.write(f"Construction proxy rows: **{row_counts.get('customer_proxy_construction_rows', 0):,}**")
            st.caption("See the project-root research report for source links and limitations.")

    st.markdown('<div style="height:0.6rem;"></div>', unsafe_allow_html=True)
    _render_competitor_tables(filtered)

    st.markdown('<div style="height:0.8rem;"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        _render_customer_proxy(str(controls["segment"]))

    _render_customer_segments()
