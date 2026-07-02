import streamlit as st

from components.styling import APP_CSS
from screens.market_opportunity import render_page as render_market_page


st.set_page_config(
    page_title="Construction Territory Growth Dashboard",
    page_icon="🗺️",
    layout="wide",
)

st.markdown(APP_CSS, unsafe_allow_html=True)
render_market_page()
st.divider()
st.markdown(
    """
    <div style="text-align: center; font-size: 0.95rem; color: #5b6472; padding: 0.25rem 0 1rem 0;">
      © 2025-2026 <b>Chia-Te Liu</b>. Author of this app.<br>
      Source code is maintained on GitHub and this app is hosted via Streamlit Community Cloud.
    </div>
    """,
    unsafe_allow_html=True,
)
