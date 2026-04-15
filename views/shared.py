from __future__ import annotations

import plotly.express as px
import streamlit as st

from models.scoring import DEFAULT_WEIGHTS, factor_catalog

TRAFFIC_SCALE = ["#ea4335", "#fbbc04", "#34a853"]


METRIC_CONFIG = {
    "market_opportunity_score": {
        "label": "Growth Opportunity",
        "short_label": "Growth",
        "description": "Prioritise territories with the strongest upside for new growth.",
    },
    "retention_health": {
        "label": "Retention Health",
        "short_label": "Health",
        "description": "Highlight territories with stronger customer retention health and resilience.",
    },
}


def render_app_frame(
    title: str = "Hilti Territory Growth Dashboard",
    subtitle: str = "Choose a city, review the map, and focus the sales team on the territories with the strongest executive case for action.",
) -> None:
    st.markdown(
        f"""
        <div class="hero">
          <h1>{title}</h1>
          <div class="muted">{subtitle}</div>
          <div class="hero-meta"><strong>Team Members</strong>: Chia-Te Liu, Ashmi Fathima, Hong Anh Bui, Prajna Ravi, Akash Somasundaran</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_controls(
    city_options: list[str],
    segment_options: list[str],
    territories_by_city: dict[str, list[str]],
    default_city: str,
) -> dict[str, str]:
    default_city_value = default_city if default_city in city_options else city_options[0]
    with st.sidebar:
        st.markdown("### Controls")
        if st.session_state.get("sidebar_city") not in city_options:
            st.session_state["sidebar_city"] = default_city_value
        if st.session_state.get("sidebar_metric_key") not in METRIC_CONFIG:
            st.session_state["sidebar_metric_key"] = "market_opportunity_score"
        city = st.selectbox(
            "City",
            options=city_options,
            key="sidebar_city",
            help="Start with the city or market area you want to review.",
        )
        metric_key = st.radio(
            "Map View",
            options=list(METRIC_CONFIG.keys()),
            format_func=lambda key: METRIC_CONFIG[key]["label"],
            key="sidebar_metric_key",
            help="Switch the map between new-growth priority and retention pressure.",
        )
        territory_options = territories_by_city.get(city, ["All territories"])
        if st.session_state.get("sidebar_territory") not in territory_options:
            st.session_state["sidebar_territory"] = "All territories"
        territory = st.selectbox(
            "Find Territory",
            options=territory_options,
            key="sidebar_territory",
            help="Use this as a search tool when you want to jump directly to a territory.",
        )
        if st.session_state.get("sidebar_segment") not in segment_options:
            st.session_state["sidebar_segment"] = segment_options[0]
        segment = st.selectbox(
            "Customer Segment",
            options=segment_options,
            key="sidebar_segment",
            help="Filter the city view by the dominant customer segment in each territory.",
        )

    return {
        "city": city,
        "metric_key": metric_key,
        "territory": territory,
        "segment": segment,
    }


def render_thi_controls(expanded: bool = False) -> dict[str, object]:
    active_keys: list[str] = []
    weights: dict[str, float] = {}

    with st.sidebar:
        with st.expander("Advanced scoring", expanded=expanded):
            st.caption(
                "Expert mode only. Adjust the factor weights when you want to show how territory ranking changes under a different scoring model."
            )
            for factor in factor_catalog():
                enabled = st.toggle(factor.label, value=True, key=f"factor_{factor.key}")
                default_weight = DEFAULT_WEIGHTS[factor.key]
                weight = st.slider(
                    f"{factor.label} weight",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(default_weight),
                    step=0.05,
                    disabled=not enabled,
                    key=f"weight_{factor.key}",
                    help=factor.description,
                )
                if enabled:
                    active_keys.append(factor.key)
                weights[factor.key] = weight

            if not active_keys:
                st.warning("All factors were switched off, so the default factor set will be used instead.")
                active_keys = [factor.key for factor in factor_catalog()]

    return {"active_keys": active_keys, "weights": weights}


def render_metric_cards(metric_payload: list[tuple[str, str, str]]) -> None:
    columns = st.columns(len(metric_payload), gap="medium")
    for column, (label, value, subtext) in zip(columns, metric_payload):
        with column:
            st.markdown(
                f"""
                <div class="metric-card">
                  <div class="metric-label">{label}</div>
                  <div class="metric-value">{value}</div>
                  <div class="metric-subtext">{subtext}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_top_territories_snapshot(df, metric_key: str) -> None:
    ranking = df.sort_values(metric_key, ascending=False).head(5).copy()
    if ranking.empty:
        return

    summary_rows = ranking.loc[:, ["PostDist", metric_key, "primary_segment"]].copy()
    summary_rows.columns = ["Territory", METRIC_CONFIG[metric_key]["short_label"], "Sales Emphasis"]
    summary_rows[METRIC_CONFIG[metric_key]["short_label"]] = summary_rows[METRIC_CONFIG[metric_key]["short_label"]].map(lambda value: f"{value:.1f}")
    st.caption("Reference only. Use the map to browse the full city footprint.")
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)


def render_market_scatter(df) -> None:
    fig = px.scatter(
        df,
        x="acquisition_opportunity",
        y="retention_health",
        size="lead_volume",
        color="market_opportunity_score",
        hover_name="PostDist",
        color_continuous_scale=TRAFFIC_SCALE,
        hover_data={
            "primary_segment": True,
            "existing_accounts": True,
            "lead_volume": True,
        },
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)


def build_territory_story(row, city_df) -> dict[str, str]:
    city_growth_avg = float(city_df["market_opportunity_score"].mean())
    city_retention_avg = float(city_df["retention_risk"].mean())
    city_competition_avg = float(city_df["competition_pressure"].mean())

    growth_gap = row["market_opportunity_score"] - city_growth_avg
    retention_gap = row["retention_risk"] - city_retention_avg
    competition_gap = row["competition_pressure"] - city_competition_avg

    if growth_gap >= 8:
        opportunity_text = "Growth upside is well above the city average, which makes this a strong candidate for near-term territory focus."
    elif growth_gap >= 0:
        opportunity_text = "Growth upside is above the city baseline and supports active pursuit if capacity is available."
    else:
        opportunity_text = "Growth upside is below the city average, so this territory is better treated as a secondary priority."

    if competition_gap >= 8:
        competition_text = "Competitive pressure appears high here, so the sales motion should emphasise sharper differentiation and stronger account planning."
    elif competition_gap >= 0:
        competition_text = "Competitive pressure is slightly above the city average, which means the area is still attractive but will require disciplined execution."
    else:
        competition_text = "Competitive pressure is relatively manageable here, which improves the odds of converting growth potential into wins."

    emphasis_options = {
        "Enterprise Projects": "Lead with enterprise project coverage, larger account planning, and consultative specification-led selling.",
        "Growth Contractors": "Lead with contractor-focused offers, fast conversion plays, and productivity-oriented sales conversations.",
        "Trade Specialists": "Lead with specialist applications, technical credibility, and narrower high-fit use cases.",
    }
    segment = row["primary_segment"]
    emphasis_text = emphasis_options.get(segment, "Lead with the strongest local segment fit and protect execution quality.")

    if retention_gap >= 8:
        retention_text = "Retention risk is also elevated, so any growth push should be paired with tighter customer coverage."
    elif retention_gap >= 0:
        retention_text = "Retention risk is present but not dominant, so growth can stay as the main story."
    else:
        retention_text = "Retention risk is lower than the city baseline, which supports an acquisition-led growth narrative."

    return {
        "opportunity_text": opportunity_text,
        "competition_text": competition_text,
        "emphasis_text": emphasis_text,
        "retention_text": retention_text,
    }


def render_territory_detail(row, city_df) -> None:
    story = build_territory_story(row, city_df)

    st.markdown(
        f"""
        <div class="detail-card">
          <div class="detail-kicker">Selected Territory</div>
          <h3>{row["PostDist"]}</h3>
          <div class="detail-grid">
            <div><span>Growth Opportunity</span><strong>{row["market_opportunity_score"]:.1f}</strong></div>
            <div><span>Retention Health</span><strong>{row["retention_health"]:.1f}</strong></div>
            <div><span>Competition Pressure</span><strong>{row["competition_pressure"]:.1f}</strong></div>
            <div><span>Primary Sales Emphasis</span><strong>{row["primary_segment"]}</strong></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("**Where should sales focus?**")
    st.write(story["opportunity_text"])
    st.write("**How competitive is the area?**")
    st.write(story["competition_text"])
    st.write("**What should managers push here?**")
    st.write(story["emphasis_text"])
    st.caption(story["retention_text"])


def render_methodology_notes() -> None:
    with st.container(border=True):
        st.subheader("How To Read This Dashboard")
        st.write(
            "This executive view is designed to help Hilti managers find the territories with the strongest growth case inside a selected city. The map is the primary decision surface, while the top-5 ranking is only a reference summary and advanced scoring stays collapsed unless an expert wants to explain the model."
        )
        st.write(
            "The current data layer mixes observed workbook fields with synthetic augmentation to provide full territory coverage for prototype demonstrations. The deployable runtime bundle is packaged in the repository data folder. Both details are intentionally kept out of the main dashboard flow and should be discussed as methodology, not as the first thing a manager sees."
        )

    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            st.subheader("Current Design Choices")
            st.write(
                """
                - City is the primary entry point for review.
                - Territory is the main unit of decision-making.
                - Growth opportunity and retention health are both visible.
                - Advanced scoring remains available but collapsed by default.
                - The main page is built as an executive dashboard, not a research sandbox.
                """
            )
    with right:
        with st.container(border=True):
            st.subheader("Known Prototype Limits")
            st.write(
                """
                - Competition and commercial emphasis are still proxy metrics.
                - Product-category recommendations are derived from segment fit, not direct product data.
                - The scoring model is still provisional and should be validated after stakeholder review.
                - Synthetic augmentation remains in the model even though it is less visible in the executive flow.
                """
            )


def render_ranking_bar(df, metric_key: str, title: str) -> None:
    ranking = df.sort_values(metric_key, ascending=False).head(15)
    fig = px.bar(
        ranking,
        x="PostDist",
        y=metric_key,
        color=metric_key,
        color_continuous_scale=TRAFFIC_SCALE,
        hover_data={"primary_segment": True, "lead_volume": True, "existing_accounts": True},
    )
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), title=title, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)
