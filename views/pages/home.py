from __future__ import annotations

import streamlit as st

from views.shared import render_app_frame, render_methodology_notes


def render_page() -> None:
    render_app_frame(
        title="Hilti Territory Growth Dashboard Methodology Notes",
        subtitle="Reference page for explaining the scoring model, prototype assumptions, deployment choices, and current design decisions behind the executive dashboard.",
    )
    render_methodology_notes()
