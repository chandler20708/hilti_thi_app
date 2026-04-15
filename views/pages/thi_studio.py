from __future__ import annotations

import json

import streamlit as st

from controllers.filters import apply_filters, get_focus_record
from models.district_data import load_prototype_geo_dataframe
from models.scoring import score_thi, summarize_metric
from views.map_component import render_leaflet_metric_map
from views.shared import render_metric_cards, render_ranking_bar, render_thi_controls


def render_page(filters: dict[str, object]) -> None:
    base = load_prototype_geo_dataframe()

    left, right = st.columns([0.92, 2.08], gap="large")
    with left:
        thi_controls = render_thi_controls()

    scored = score_thi(base, thi_controls["weights"], thi_controls["active_keys"])
    filtered = apply_filters(scored, filters)
    scope_frame = filtered if not filtered.empty else scored
    geojson_data = json.dumps(json.loads(scope_frame.to_json()))
    focus = get_focus_record(base, filters)
    summary = summarize_metric(scope_frame, "thi_score")

    mean_value = summary["mean_value"]
    top_value = summary["top_value"]

    with right:
        render_metric_cards(
            [
                ("Districts in scope", str(summary["count"]), "After the current filters"),
                ("Average THI", f"{mean_value:.1f}" if mean_value is not None else "N/A", "Prototype MCDA score"),
                ("Top district", summary["top_district"] or "N/A", f"Score {top_value:.1f}" if top_value is not None else "No score"),
                ("Active factors", str(len(thi_controls["active_keys"])), "Current THI criteria"),
            ]
        )

        top, bottom = st.columns([1.35, 1], gap="large")
        with top:
            st.markdown('<div class="shell">', unsafe_allow_html=True)
            st.subheader("THI Studio")
            st.caption(
                "This page is the research-facing sandbox. For now it uses a weighted-sum MCDA prototype over synthetic criteria, so the pipeline can be discussed before the post-meeting THI definition is finalized."
            )
            render_leaflet_metric_map(
                geojson_data=geojson_data,
                filters=filters,
                metric_key="thi_score",
                metric_label="Territorial Health Index",
                focus_record=focus,
                should_refocus=False,
                focus_district=filters.get("district"),
                weights=thi_controls["weights"],
                active_keys=thi_controls["active_keys"],
                height=720,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with bottom:
            st.markdown('<div class="shell">', unsafe_allow_html=True)
            st.subheader("Prototype THI Ranking")
            render_ranking_bar(filtered if not filtered.empty else scored, "thi_score", "Top prototype THI districts")
            st.markdown("</div>", unsafe_allow_html=True)
