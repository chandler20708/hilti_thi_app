import streamlit as st

from components.styling import APP_CSS
from screens.external_market import render_page


st.set_page_config(
    page_title="External Market Intelligence",
    page_icon="📍",
    layout="wide",
)

st.markdown(APP_CSS, unsafe_allow_html=True)
render_page()
