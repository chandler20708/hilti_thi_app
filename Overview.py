import streamlit as st

from views.pages.market_opportunity import render_page as render_market_page
from views.styling import APP_CSS


st.set_page_config(
    page_title="Hilti Territory Growth Dashboard",
    page_icon="🗺️",
    layout="wide",
)

st.markdown(APP_CSS, unsafe_allow_html=True)
render_market_page()
