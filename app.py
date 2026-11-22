"""Launch the public demo or the full local CreditRisk 360 application."""

import os
import streamlit as st

from creditrisk.dashboard.ui import CSS
from creditrisk.paths import ARTIFACTS, DATABASE

st.set_page_config(page_title="CreditRisk 360", layout="wide", initial_sidebar_state="auto")
st.markdown(CSS, unsafe_allow_html=True)

mode = os.getenv("CREDITRISK_MODE", "auto")
if mode not in {"auto", "public", "local"}:
    st.title("CreditRisk 360")
    st.error("CREDITRISK_MODE must be auto, public, or local.")
    st.stop()

local_files = (DATABASE, ARTIFACTS / "loan_scores.parquet", ARTIFACTS / "fit_manifest.json")
public = mode == "public" or (mode == "auto" and not any(path.exists() for path in local_files))
if public:
    from creditrisk.dashboard import public_data, public_pages

    try:
        current, tables = public_data.load(public_data.release_key())
    except (OSError, ValueError, KeyError):
        st.title("CreditRisk 360")
        st.error("The aggregate public release could not be validated. Check the committed deployment files.")
        st.stop()
    st.info("Public demo · Fixed aggregate views, pooled sparse segments, and no loan-level filters.")
    renderers = [
        lambda: public_pages.executive(tables),
        lambda: public_pages.model_lab(current, tables),
        lambda: public_pages.risk_explorer(tables),
        lambda: public_pages.stress_testing(tables),
        lambda: public_pages.model_governance(current, tables),
    ]
else:
    import duckdb
    from creditrisk.dashboard import explorer, governance, lab, overview, stress
    from creditrisk.dashboard.data import release, release_key

    try:
        key = release_key()
        current = release(key)
    except (OSError, ValueError, KeyError, duckdb.Error) as error:
        st.title("CreditRisk 360")
        st.error("The local portfolio and model release could not be validated.")
        st.caption(str(error))
        st.markdown("Follow the README to rebuild the database, train the models, and regenerate the score artifacts.")
        st.stop()
    renderers = [lambda render=page.render: render(key, current)
                 for page in (overview, lab, explorer, stress, governance)]

pages = [
    st.Page(renderers[0], title="Executive overview", default=True),
    st.Page(renderers[1], title="Model lab", url_path="model-lab"),
    st.Page(renderers[2], title="Risk explorer", url_path="risk-explorer"),
    st.Page(renderers[3], title="Stress testing", url_path="stress-testing"),
    st.Page(renderers[4], title="Model governance", url_path="governance"),
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
