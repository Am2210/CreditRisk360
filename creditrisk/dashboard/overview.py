"""Executive views of the eligible historical portfolio."""

import plotly.graph_objects as go
import streamlit as st

from .data import Scope, aggregates
from .ui import AMOUNT_HELP, BLUE, OBSERVED_HELP, TEAL, approval_bars, cards, chart, export, grouped, money, panel, pct, title


def render(key, release):
    title("Executive portfolio overview", "SBA 7(a) · Eligible funded records from FY2010–FY2019 approvals")
    totals = aggregates(key, Scope("all"), ("portfolio", "vintage", "industry", "state", "size", "collateral"),
                        release["champion"])
    stats = grouped(totals, "portfolio").iloc[0]
    cards(
        ("Eligible loan records", f"{stats.records:,.0f}", "Distinct source records meeting the five-year eligibility rule."),
        ("Gross approved principal", money(stats.approved_usd), AMOUNT_HELP),
        ("Five-year charge-off rate", pct(stats.observed_rate), OBSERVED_HELP),
        ("Recorded five-year events", f"{stats.events:,.0f}", "Recorded SBA charge-offs within the eligible window."),
    )
    st.caption("Gross approved principal measures historical commitments. Outstanding balances are unavailable.")

    vintage = grouped(totals, "vintage").sort_values("segment")
    left, right = st.columns([1.6, 1])
    with panel("overview_vintage", left):
        st.subheader("Vintage charge-off performance")
        st.caption("Five-year recorded frequency by first-disbursement fiscal year")
        fig = go.Figure(go.Scatter(
            x=vintage.segment, y=vintage.observed_rate, mode="lines+markers",
            line={"color": TEAL, "width": 3}, marker={"size": 7},
            customdata=list(zip(vintage.records, vintage.events)),
            hovertemplate="FY%{x}<br>%{y:.2%} observed<br>%{customdata[1]:,.0f} events"
                          " / %{customdata[0]:,.0f} records<extra></extra>",
        ))
        fig.update_xaxes(type="category", title="First-disbursement fiscal year", showgrid=False)
        fig.update_yaxes(title="Charge-off frequency", rangemode="tozero")
        chart(fig, key="overview_vintage", percent_y=True)
    with panel("overview_mix", right):
        st.subheader("Portfolio composition")
        composition = st.selectbox("Composition by", ["size", "collateral"],
                                   format_func={"size": "Approved loan size", "collateral": "Reported collateral"}.get,
                                   label_visibility="collapsed")
        mix = grouped(totals, composition)
        fig = go.Figure(go.Pie(
            labels=mix.segment, values=mix.records, hole=0.67, textinfo="none", sort=False,
            domain={"y": [0, 0.82]},
            marker={"colors": ["#426784", "#117867", "#829bae", "#335166", "#a4c2bf", "#ccdae6"]},
            hovertemplate="%{label}<br>%{value:,} records · %{percent:.1%}<extra></extra>",
        ))
        fig.add_annotation(x=0.5, y=0.41, text=f"<b>{stats.records:,.0f}</b><br>records",
                           showarrow=False, font={"size": 15})
        chart(fig, key="overview_mix", height=284)

    left, right = st.columns(2)
    for column, dimension, label in ((left, "industry", "Largest industry approvals"),
                                      (right, "state", "Largest project-state approvals")):
        with panel(f"overview_{dimension}", column):
            st.subheader(label)
            st.caption("Top eight by historical gross approved principal")
            chart(approval_bars(grouped(totals, dimension, top=8)), key=f"overview_{dimension}", height=320)

    with panel("overview_volume"):
        st.subheader("Historical approval volume by vintage")
        st.caption("FY2020–2021 disbursements reflect loans approved in earlier fiscal years")
        fig = go.Figure(go.Bar(x=vintage.segment, y=vintage.approved_usd / 1e9, marker_color=BLUE,
                               customdata=vintage.records,
                               hovertemplate="FY%{x}<br>$%{y:.2f}B approved<br>%{customdata:,} records<extra></extra>"))
        fig.update_xaxes(type="category", title="First-disbursement fiscal year", showgrid=False)
        fig.update_yaxes(title="Approved principal (USD billions)")
        chart(fig, key="overview_volume", height=240)
    export(totals.drop(columns=["predicted_rate", "expected_events"]), "portfolio_overview.csv", "Download portfolio aggregates")
