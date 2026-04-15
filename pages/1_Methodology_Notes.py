import streamlit as st

from views.pages.home import render_page as render_home_page
from views.styling import APP_CSS


st.set_page_config(
    page_title="Methodology Notes",
    page_icon="📘",
    layout="wide",
)

st.markdown(APP_CSS, unsafe_allow_html=True)
render_home_page()
