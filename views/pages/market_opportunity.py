from __future__ import annotations

import streamlit as st

from controllers.filters import apply_filters, get_focus_record
from models.district_data import get_filter_options, load_prototype_geo_dataframe
from models.scoring import score_thi
from models.store_locations import load_hilti_store_locations
from services.map_service import ensure_map_service
from views.map_component import render_leaflet_metric_map
from views.shared import (
    METRIC_CONFIG,
    render_app_frame,
    render_sidebar_controls,
    render_metric_cards,
    render_top_territories_snapshot,
    render_territory_detail,
    render_thi_controls,
)


def render_page() -> None:
    base = load_prototype_geo_dataframe()
    options = get_filter_options(base)
    store_locations = load_hilti_store_locations()
    server_url = ensure_map_service(base)

    render_app_frame()
    city_options = options["sprawls"]
    default_city = "Manchester" if "Manchester" in city_options else city_options[0]

    territories_by_city = {"All": ["All territories"] + sorted(base["PostDist"].dropna().unique().tolist())}
    for city in [value for value in city_options if value != "All"]:
        city_scope = base.loc[base["Sprawl"] == city]
        territories_by_city[city] = ["All territories"] + sorted(city_scope["PostDist"].dropna().unique().tolist())

    controls = render_sidebar_controls(city_options, options["segments"], territories_by_city, default_city)
    st.session_state["executive_city"] = controls["city"]

    thi_controls = render_thi_controls(expanded=False)
    scored = score_thi(base, thi_controls["weights"], thi_controls["active_keys"])

    analysis_filters = {
        "district": "All",
        "post_area": "All",
        "sprawl": controls["city"],
        "segment": controls["segment"],
        "observed_only": False,
    }

    scope_frame = apply_filters(scored, analysis_filters)
    if scope_frame.empty:
        scope_frame = scored

    visible_stores = store_locations
    if controls["city"] != "All":
        visible_stores = store_locations.loc[store_locations["city"] == controls["city"]]

    metric_key = controls["metric_key"]
    metric_meta = METRIC_CONFIG[metric_key]
    top_priority = scope_frame.sort_values(metric_key, ascending=False).head(1)
    top_territory = top_priority.iloc[0]["PostDist"] if not top_priority.empty else "N/A"
    avg_growth = float(scope_frame["market_opportunity_score"].mean()) if not scope_frame.empty else 0.0
    avg_retention = float(scope_frame["retention_health"].mean()) if not scope_frame.empty else 0.0

    render_metric_cards(
        [
            ("City in focus", controls["city"], "Primary executive review area"),
            ("Average growth opportunity", f"{avg_growth:.1f}", "Current city-wide territory average"),
            ("Average retention health", f"{avg_retention:.1f}", "Higher values mean stronger retention health"),
            ("Top priority territory", top_territory, f"Highest {metric_meta['short_label'].lower()} signal in scope"),
        ],
        scope_frame=scope_frame
    )
    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

    searched_territory = controls["territory"] if controls["territory"] != "All territories" else None
    selected_territory = searched_territory

    focus_filters = {
        "district": selected_territory or "All",
        "post_area": "All",
        "sprawl": controls["city"],
        "segment": controls["segment"],
        "observed_only": False,
    }
    focus = get_focus_record(base, focus_filters)

    geography_signature = (controls["city"], selected_territory or "All", metric_key)
    previous_signature = st.session_state.get("market_geo_signature")
    should_refocus = previous_signature != geography_signature
    st.session_state["market_geo_signature"] = geography_signature

    left, right = st.columns([1.7, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader(f"{metric_meta['label']} Map")
            st.caption(f"{metric_meta['description']} Browse the full city on the map, or use the sidebar search to jump to a specific territory.")
            render_leaflet_metric_map(
                server_url=server_url,
                filters=analysis_filters,
                metric_key=metric_key,
                metric_label=metric_meta["label"],
                focus_record=focus,
                should_refocus=should_refocus,
                store_locations=visible_stores.to_dict("records"),
                focus_district=selected_territory,
                weights=thi_controls["weights"],
                active_keys=thi_controls["active_keys"],
                height=720,
            )

    selected_row = None
    if selected_territory:
        match = scope_frame.loc[scope_frame["PostDist"] == selected_territory]
        if not match.empty:
            selected_row = match.iloc[0]

    with right:
        with st.container(border=True):
            st.subheader("Territory Action View")
            if selected_row is not None:
                render_territory_detail(selected_row, scope_frame)
            else:
                st.info("Use the sidebar territory search to focus the map on a specific territory and open its executive summary.")

        with st.container(border=True):
            st.subheader(f"Top 5 {metric_meta['label']} Territories")
            render_top_territories_snapshot(scope_frame, metric_key)
