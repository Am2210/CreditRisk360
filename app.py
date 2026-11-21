"""Launch the local CreditRisk 360 Streamlit application."""

import duckdb
import streamlit as st

from creditrisk.dashboard import explorer, governance, lab, overview, stress
from creditrisk.dashboard.data import release, release_key
from creditrisk.dashboard.ui import CSS

st.set_page_config(page_title="CreditRisk 360", layout="wide", initial_sidebar_state="auto")
st.markdown(CSS, unsafe_allow_html=True)

try:
    key = release_key()
    current = release(key)
except (OSError, ValueError, KeyError, duckdb.Error) as error:
    st.title("CreditRisk 360")
    st.error("The local portfolio and model release could not be validated.")
    st.caption(str(error))
    st.markdown("Follow the README to rebuild the database, train the models, and regenerate the score artifacts.")
    st.stop()

pages = [
    st.Page(lambda: overview.render(key, current), title="Executive overview", default=True),
    st.Page(lambda: lab.render(key, current), title="Model lab", url_path="model-lab"),
    st.Page(lambda: explorer.render(key, current), title="Risk explorer", url_path="risk-explorer"),
    st.Page(lambda: stress.render(key, current), title="Stress testing", url_path="stress-testing"),
    st.Page(lambda: governance.render(key, current), title="Model governance", url_path="governance"),
]
active = st.navigation(pages, position="hidden")
with st.sidebar:
    st.markdown('<div class="cr-brand">CreditRisk 360</div><div class="cr-side-caption">SBA 7(a) risk analytics</div>',
                unsafe_allow_html=True)
    st.space("small")
    for page in pages:
        st.page_link(page, label=page.title)
    st.markdown(f'<div class="cr-side-caption cr-side-snapshot">SBA FOIA snapshot<br>{current["snapshot"]}</div>',
                unsafe_allow_html=True)
active.run()
