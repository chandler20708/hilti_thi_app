from __future__ import annotations

import json

import streamlit as st

from controllers.filters import apply_filters, get_focus_record
from models.district_data import build_map_frame, get_filter_options, load_prototype_geo_dataframe
from models.external_market import build_overview_external_context
from models.scoring import score_thi
from models.store_locations import load_hilti_store_locations
from components.map_component import render_leaflet_metric_map
from components.shared import (
    METRIC_CONFIG,
    render_app_frame,
    build_analysis_filters,
    map_data_source_caption,
    resolve_api_base_url,
    render_sidebar_controls,
    render_metric_cards,
    render_top_territories_snapshot,
    render_territory_detail,
    render_thi_controls,
)


def _render_external_context_panel(visible_stores, selected_local_authority: str) -> None:
    store_names = tuple(visible_stores["name"].dropna().astype(str).tolist())
    context = build_overview_external_context(store_names, selected_local_authority)
    pressure = context["authority_pressure_summary"]
    demand = context["demand_summary"]
    chain_table = context["authority_competitors_by_chain"].head(8).copy()

    st.markdown(
        f"""
        <div class="external-context">
          <div>
            <div class="external-kicker">External pressure</div>
            <strong>{pressure["locations"]:,} mapped competitor locations</strong>
            <span>{pressure["chains"]:,} chains in {pressure["area"]}; largest mapped chain is {pressure["top_competitor"]}.</span>
          </div>
          <div>
            <div class="external-kicker">Construction demand</div>
            <strong>{demand["construction_units"]:,} local construction units</strong>
            <span>{demand["area"]} has {demand["units_per_10k_people"]:.1f} units per 10k people across a population of {demand["population"]:,}.</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("External signal detail", expanded=False):
        st.caption(
            "External pressure is now counted inside the selected local authority. Construction demand uses the same local authority. These signals do not recalculate the THI score yet."
        )
        if chain_table.empty:
            st.info("No mapped competitor locations for the selected local authority.")
        else:
            display = chain_table.rename(
                columns={
                    "competitor": "Competitor",
                    "mapped_locations": "Mapped locations",
                    "direct_threat_locations": "Within 10km of a construction hub",
                }
            )
            st.dataframe(display, width="stretch", hide_index=True)


def render_page() -> None:
    base = load_prototype_geo_dataframe()
    options = get_filter_options(base)
    store_locations = load_hilti_store_locations()

    render_app_frame()
    local_authority_options = options["local_authorities"]
    default_local_authority = "All" if "All" in local_authority_options else local_authority_options[0]

    territories_by_local_authority = {
        "All": ["All territories"] + sorted(base["PostDist"].dropna().unique().tolist())
    }
    for local_authority in [value for value in local_authority_options if value != "All"]:
        authority_scope = base.loc[base["local_authority_name"] == local_authority]
        territories_by_local_authority[local_authority] = [
            "All territories"
        ] + sorted(authority_scope["PostDist"].dropna().unique().tolist())

    controls = render_sidebar_controls(
        local_authority_options,
        options["segment_modes"],
        options["segments_by_mode"],
        territories_by_local_authority,
        default_local_authority,
    )
    st.session_state["executive_city"] = controls["local_authority"]
    api_base_url = resolve_api_base_url()

    thi_controls = render_thi_controls(expanded=False)
    scored = score_thi(base, thi_controls["weights"], thi_controls["active_keys"])

    analysis_filters = build_analysis_filters(
        controls["local_authority"],
        controls["segment"],
        segment_mode=controls["segment_mode"],
    )

    scope_frame = apply_filters(scored, analysis_filters)
    geojson_data = None
    if not api_base_url:
        map_frame = build_map_frame(scope_frame, controls["local_authority"])
        geojson_data = json.dumps(json.loads(map_frame.to_json()))

    visible_stores = store_locations
    if controls["local_authority"] != "All" and "local_authority_name" in store_locations.columns:
        visible_stores = store_locations.loc[
            (store_locations["local_authority_name"] == controls["local_authority"])
            | (store_locations["city"] == controls["local_authority"])
        ]

    metric_key = controls["metric_key"]
    metric_meta = METRIC_CONFIG[metric_key]
    top_priority = scope_frame.nlargest(1, metric_key)
    top_territory = top_priority.iloc[0]["PostDist"] if not top_priority.empty else "N/A"
    avg_opportunity = float(scope_frame["thi_score"].mean()) if not scope_frame.empty else 0.0
    avg_growth = float(scope_frame["market_opportunity_score"].mean()) if not scope_frame.empty else 0.0
    avg_retention = float(scope_frame["retention_health"].mean()) if not scope_frame.empty else 0.0
    segment_label = controls["segment"] if controls["segment"] != "All" else controls["segment_mode"].replace("_", " ").title()

    render_metric_cards(
        [
            ("Geography in scope", controls["local_authority"], "Selected local authority"),
            ("Segment slice", segment_label, "Current customer segment filter"),
            ("Average opportunity score", f"{avg_opportunity:.1f}", "THI average inside the selected segment"),
            ("Top deployment candidate", top_territory, f"Highest {metric_meta['short_label'].lower()} signal in scope"),
        ],
        scope_frame=scope_frame
    )
    _render_external_context_panel(visible_stores, controls["local_authority"])
    if scope_frame.empty:
        st.warning("No territories match the current geography and segment slice. Broaden the segment filter or switch local authority scope.")
    st.markdown('<div style="height:0.4rem;"></div>', unsafe_allow_html=True)

    searched_territory = controls["territory"] if controls["territory"] != "All territories" else None
    selected_territory = searched_territory

    focus_filters = build_analysis_filters(
        controls["local_authority"],
        controls["segment"],
        district=selected_territory or "All",
        segment_mode=controls["segment_mode"],
    )
    focus = get_focus_record(base, focus_filters)

    geography_signature = (
        controls["local_authority"],
        controls["segment_mode"],
        controls["segment"],
        selected_territory or "All",
        metric_key,
    )
    previous_signature = st.session_state.get("market_geo_signature")
    should_refocus = previous_signature != geography_signature
    st.session_state["market_geo_signature"] = geography_signature

    left, right = st.columns([2.15, 0.85], gap="medium")
    with left:
        with st.container(border=True):
            st.subheader(f"{metric_meta['label']} Map")
            overview_note = (
                " National overview uses point mode for faster inline loading."
                if controls["local_authority"] == "All" and not api_base_url
                else ""
            )
            st.caption(
                f"{metric_meta['description']} Browse the full local authority on the map, or use the sidebar search to jump to a specific territory.{overview_note}"
            )
            if controls["segment"] != "All":
                st.caption(
                    f"Cross-filter active: showing {metric_meta['label'].lower()} only for "
                    f"{controls['segment']} within {controls['local_authority']}."
                )
            map_data_source_caption(api_base_url)
            render_leaflet_metric_map(
                geojson_data=geojson_data,
                metric_key=metric_key,
                metric_label=metric_meta["label"],
                focus_record=focus,
                should_refocus=should_refocus,
                api_base_url=api_base_url or None,
                filters=analysis_filters,
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
            st.subheader(f"Top 5 Deployment Candidates")
            render_top_territories_snapshot(scope_frame, metric_key, controls["segment_mode"])
