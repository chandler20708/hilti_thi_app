from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
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


def build_analysis_filters(city: str, segment: str, district: str = "All") -> dict[str, str]:
    return {
        "district": district,
        "sprawl": city,
        "segment": segment,
    }


def _normalize_api_base_url(raw: object | None) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1].strip()
    return s.rstrip("/")


def _api_url_from_mapping(obj: Any) -> str:
    if not isinstance(obj, Mapping):
        return ""
    for key in ("API_BASE_URL", "api_base_url", "HILTI_API_BASE_URL", "hilti_api_base_url"):
        if key not in obj:
            continue
        url = _normalize_api_base_url(obj[key])
        if url:
            return url
    return ""


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


def _parse_boolish(raw: object | None) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    return None


def resolve_use_vector_tiles() -> bool:
    """Use MapLibre + MVT when True; default False so `/districts` stays primary."""
    for key in ("HILTI_USE_VECTOR_TILES", "USE_VECTOR_TILES"):
        hit = _parse_boolish(os.getenv(key))
        if hit is not None:
            return hit
    try:
        list(st.secrets.keys())
    except Exception:
        pass
    try:
        for key in ("HILTI_USE_VECTOR_TILES", "use_vector_tiles"):
            if key not in st.secrets:
                continue
            hit = _parse_boolish(st.secrets[key])
            if hit is not None:
                return hit
        for section in ("theme", "api", "map", "hilti", "streamlit"):
            if section not in st.secrets:
                continue
            sec = st.secrets[section]
            if not isinstance(sec, Mapping):
                continue
            for key in ("HILTI_USE_VECTOR_TILES", "use_vector_tiles"):
                if key not in sec:
                    continue
                hit = _parse_boolish(sec[key])
                if hit is not None:
                    return hit
    except Exception:
        pass
    return False


def resolve_api_base_url() -> str:
    """Resolve the map API base URL at call time (no trailing slash).

    Streamlit copies top-level string secrets into ``os.environ`` the first time
    secrets are parsed. Reading ``API_BASE_URL`` only when ``config`` is imported
    often misses Cloud secrets, so we touch ``st.secrets`` then read the
    environment and secret keys again.
    """
    try:
        list(st.secrets.keys())
    except Exception:
        pass

    for key in ("API_BASE_URL", "HILTI_API_BASE_URL"):
        url = _normalize_api_base_url(os.getenv(key))
        if url:
            return url

    try:
        for key in ("API_BASE_URL", "api_base_url", "HILTI_API_BASE_URL", "hilti_api_base_url"):
            if key not in st.secrets:
                continue
            url = _normalize_api_base_url(st.secrets[key])
            if url:
                return url
        # TOML: keys that appear after a ``[theme]`` header are nested under ``theme``,
        # so Cloud secrets like ``[theme]`` / ``base = "light"`` / ``API_BASE_URL = "..."``
        # store the URL at ``st.secrets["theme"]["API_BASE_URL"]``, not top-level.
        for section in ("theme", "api", "map", "hilti", "streamlit"):
            if section not in st.secrets:
                continue
            url = _api_url_from_mapping(st.secrets[section])
            if url:
                return url
    except Exception:
        pass

    return ""


def map_data_source_caption(api_base_url: str) -> None:
    if api_base_url:
        if resolve_use_vector_tiles():
            st.caption(
                "Territory polygons: MapLibre vector tiles from your API `/tiles/{z}/{x}/{y}.mvt` "
                "(experimental; set `HILTI_USE_VECTOR_TILES=0` to keep the lighter `/districts` viewport mode)."
            )
        else:
            st.caption(
                "Territory polygons: live API (Leaflet viewport requests to your hosted `/districts` endpoint). "
                "Optional: set `HILTI_USE_VECTOR_TILES=1` only if you want to try the experimental MapLibre vector-tile mode."
            )
    else:
        st.caption(
            "Territory polygons: bundled inline data. Set `API_BASE_URL` in Streamlit secrets, "
            "or set the `API_BASE_URL` / `HILTI_API_BASE_URL` environment variable, to use the FastAPI map service."
        )


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

def _render_mini_distribution(values):
    if len(values) == 0:
        return

    mean_val = values.mean()

    fig = go.Figure()

    # distribution
    fig.add_trace(go.Histogram(
        x=values,
        nbinsx=20,
        marker=dict(color="rgba(120,140,160,0.18)"),
    ))

    # mean marker (THIS is the key for interpretation)
    fig.add_vline(
        x=mean_val,
        line_width=2,
        line_color="rgba(16,24,40,0.5)"
    )

    fig.update_layout(
        height=30,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False}
    )
    st.markdown(
        '<div style="margin-top:-8px;"></div>',
        unsafe_allow_html=True
    )


def render_metric_cards(metric_payload, scope_frame=None) -> None:
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

            # --- Mini distribution for growth ---
            if scope_frame is not None:
                if label == "Average growth opportunity":
                    values = scope_frame["market_opportunity_score"].dropna()
                    _render_mini_distribution(values)

                elif label == "Average retention health":
                    values = scope_frame["retention_health"].dropna()
                    _render_mini_distribution(values)

def render_top_territories_snapshot(df, metric_key: str) -> None:
    ranking = df.sort_values(metric_key, ascending=False).head(5).copy()
    if ranking.empty:
        return

    summary_rows = ranking.loc[:, ["PostDist", metric_key, "primary_segment"]].copy()
    summary_rows.columns = ["Territory", METRIC_CONFIG[metric_key]["short_label"], "Sales Emphasis"]
    summary_rows[METRIC_CONFIG[metric_key]["short_label"]] = summary_rows[METRIC_CONFIG[metric_key]["short_label"]].map(lambda value: f"{value:.1f}")
    st.caption("Reference only. Use the map to browse the full city footprint.")
    st.dataframe(summary_rows, width="stretch", hide_index=True)


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
            "The current data layer mixes observed workbook fields with synthetic augmentation to provide full territory coverage for prototype demonstrations. The deployable runtime bundle is packaged in the app-local data folder. Both details are intentionally kept out of the main dashboard flow and should be discussed as methodology, not as the first thing a manager sees."
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
    st.plotly_chart(fig, width="stretch")
