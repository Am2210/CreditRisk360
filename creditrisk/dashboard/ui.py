"""Shared presentation, chart styles, and portfolio filter controls."""

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .data import FILTER_FIELDS, Scope, filter_options, sector_label

INK = "#182b40"
BLUE = "#426784"
TEAL = "#117867"
MUTED = "#586c81"
SLATE = "#77899b"
GOLD = "#a06537"
LINE = "#dde6ef"
MODEL_COLORS = {"logistic": SLATE, "random_forest": BLUE, "xgboost": TEAL}
AMOUNT_HELP = "Historical gross approvals in dollars. Current principal balances are unavailable."
OBSERVED_HELP = "Recorded SBA charge-offs within 60 calendar months divided by eligible funded records."
PREDICTED_HELP = "Mean frozen five-year modeled charge-off probability across the selected records."
COHORT_LABELS = {
    "test": "FY2018–2019 holdout",
    "selection": "FY2017 selection cohort",
    "score_only": "FY2020–2021 delayed disbursements",
    "all": "All eligible records (includes training)",
}

CSS = """
<style>
.stApp { background: #edf2f7; }
[data-testid="stHeader"] { background: rgba(237,242,247,.94); }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stMainBlockContainer"] {
  padding: 3.75rem clamp(1rem, 3.2vw, 3rem) 3.5rem;
  max-width: 1620px;
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding: 1.5rem 1rem; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
  color: #e3edf5; border-radius: 7px; padding: .5rem .65rem; font-weight: 520;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: #20364b; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
  background: #213b4d; border-left: 3px solid #70dbbf;
}
.cr-brand { font-size: 1.24rem; font-weight: 750; letter-spacing: -.025em; color: #f5f9fc; }
.cr-side-caption { color: #a7bed2; margin-top: .2rem; font-size: .875rem; }
.cr-side-snapshot { padding-top: .65rem; border-top: 1px solid #30475e; line-height: 1.65; }
.cr-hero {
  background: #13263b; border: 1px solid #243e58; border-left: 4px solid #40ab94;
  border-radius: 12px; padding: 1.05rem 1.4rem 1.1rem; margin-bottom: .1rem;
}
.cr-hero h1 {
  color: #f5f9fc; font-size: clamp(1.65rem, 3.1vw, 2.35rem);
  padding: 0; margin: 0; letter-spacing: -.038em; line-height: 1.2;
}
.cr-hero p { color: #c5d4e1; margin: .45rem 0 0; font-size: .94rem; }
[data-testid="stMetric"] {
  background: #fff; border: 1px solid #dce5ee; border-radius: 10px;
  padding: .8rem .85rem; min-height: 100px;
}
[data-testid="stMetricLabel"] p {
  color: #53677b; font-weight: 650; font-size: .875rem;
  white-space: normal; overflow: visible;
}
[data-testid="stMetricValue"] { font-size: clamp(1.1rem, 2.05vw, 1.95rem); font-weight: 730; letter-spacing: -.03em; }
[class*="st-key-panel_"], [data-testid="stForm"] {
  background: #fff; border-radius: 11px; border-color: #dce5ee;
}
h2, h3 { letter-spacing: -.022em; }
[data-testid="stCaptionContainer"] { color: #586c81; }
@media (max-width: 800px) {
  [data-testid="stMainBlockContainer"] { padding-top: 3.25rem; }
  .cr-hero { padding: .9rem 1rem; }
}
</style>
"""


def title(name, detail):
    st.markdown(
        f'<div class="cr-hero"><h1>{escape(name)}</h1><p>{escape(detail)}</p></div>',
        unsafe_allow_html=True,
    )


def money(value):
    for scale, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= scale:
            return f"${value / scale:,.2f}{suffix}"
    return f"${value:,.0f}"


def pct(value):
    return f"{value:.2%}" if value is not None and pd.notna(value) else "—"


def cards(*items):
    for column, (name, value, help_text) in zip(st.columns(len(items)), items):
        column.metric(name, value, help=help_text, border=True)


def panel(key, parent=st):
    return parent.container(border=True, key=f"panel_{key}")


def chart(fig, *, key, height=300, percent_x=False, percent_y=False):
    fig.update_layout(
        template="plotly_white", height=height, paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "size": 13, "color": INK},
        margin={"l": 8, "r": 12, "t": 12, "b": 8}, hoverlabel={"bgcolor": INK, "font_color": "#ffffff"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "font": {"size": 12}},
    )
    fig.update_xaxes(gridcolor=LINE, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=LINE, zeroline=False, automargin=True)
    if percent_x:
        fig.update_xaxes(tickformat=".0%")
    if percent_y:
        fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch", theme=None, key=key,
                    config={"displaylogo": False, "scrollZoom": False})


def export(frame, filename, label="Download CSV"):
    st.download_button(label, frame.to_csv(index=False).encode("utf-8-sig"),
                       file_name=filename, mime="text/csv", key=filename, on_click="ignore")


def filters(key, model, namespace):
    choices = filter_options(key, model)
    with st.form(f"{namespace}_scope"):
        cols = st.columns(3)
        cohort = cols[0].selectbox("Portfolio cohort", list(COHORT_LABELS), format_func=COHORT_LABELS.get,
                                   key=f"{namespace}_cohort")
        selections = []
        for index, (field, label) in enumerate(FILTER_FIELDS.items(), 1):
            formatter = sector_label if field == "industry" else str
            values = cols[index % 3].multiselect(
                label, choices[field], format_func=formatter,
                placeholder="All", key=f"{namespace}_{field}",
                help="Filtering uses reported term bands. Term is excluded from model estimation."
                if field == "term" else None,
            )
            selections.append((field, tuple(sorted(values))))
        st.form_submit_button("Apply filters", type="primary")
    if cohort == "all":
        st.caption("This scope includes in-sample training scores. Use the holdout for model evaluation.")
    if cohort == "score_only":
        st.caption("This cohort contains delayed disbursements from earlier approvals and was scored outside model evaluation.")
    return Scope(cohort, tuple(selections))


def grouped(frame, dimension, *, top=None, by="approved_usd"):
    subset = frame.loc[frame.dimension.eq(dimension)].copy()
    subset["label"] = subset.segment.map(sector_label) if dimension == "industry" else subset.segment
    return subset.nlargest(top, by).sort_values(by) if top else subset


def approval_bars(frame):
    labels = frame["label"].map(lambda label: label if len(label) <= 33 else label[:31] + "…")
    fig = go.Figure(go.Bar(
        x=frame.approved_usd / 1e9, y=labels, orientation="h", marker_color=BLUE,
        customdata=list(zip(frame.label, frame.approved_usd, frame.records)),
        hovertemplate="%{customdata[0]}<br>Approved $%{customdata[1]:,.0f}"
                      "<br>%{customdata[2]:,} records<extra></extra>",
    ))
    fig.update_xaxes(title="Gross approved principal (USD billions)")
    fig.update_yaxes(showgrid=False)
    return fig
