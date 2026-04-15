import streamlit as st

from components.styling import APP_CSS
from screens.methodology import render_page as render_home_page


st.set_page_config(
    page_title="Methodology Notes",
    page_icon="📘",
    layout="wide",
)

st.markdown(APP_CSS, unsafe_allow_html=True)
render_home_page()
