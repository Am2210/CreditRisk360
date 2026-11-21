"""Segment-level portfolio risk using the frozen validation risk groups."""

import plotly.graph_objects as go
import streamlit as st

from .data import FILTER_FIELDS, MODELS, aggregates
from .ui import (
    AMOUNT_HELP, BLUE, OBSERVED_HELP, PREDICTED_HELP, TEAL,
    cards, chart, export, filters, grouped, money, panel, pct, title,
)


def render(key, release):
    model = release["champion"]
    title("Portfolio risk explorer", f"Filter the portfolio and compare observed charge-offs with frozen {MODELS[model]} scores.")
    scope = filters(key, model, "explorer")
    data = aggregates(key, scope, ("portfolio", "decile", *FILTER_FIELDS), model)
    if data.empty:
        st.info("No records match this cohort and filter combination. Clear a filter or select a different cohort.")
        return
    totals = grouped(data, "portfolio").iloc[0]
    cards(
        ("Matched loan records", f"{totals.records:,.0f}", "Count of eligible records matching all applied filters."),
        ("Gross approved principal", money(totals.approved_usd), AMOUNT_HELP),
        ("Five-year charge-off rate", pct(totals.observed_rate), OBSERVED_HELP),
        ("Mean modeled probability", pct(totals.predicted_rate), PREDICTED_HELP),
    )
    left, right = st.columns([1.05, 1])
    with panel("explorer_deciles", left):
        st.subheader("Observed and predicted by risk decile")
        st.caption("Decile boundaries were fixed on FY2017 validation. Your selection can have uneven group sizes.")
        deciles = grouped(data, "decile").assign(order=lambda rows: rows.segment.astype(int)).sort_values("order")
        fig = go.Figure()
        for field, label, color in (("observed_rate", "Observed", BLUE), ("predicted_rate", "Modeled", TEAL)):
            fig.add_bar(x=deciles.order, y=deciles[field], name=label, marker_color=color,
                        customdata=deciles.records,
                        hovertemplate="Decile %{x}<br>%{y:.2%} · %{customdata:,} records<extra>%{fullData.name}</extra>")
        fig.update_layout(barmode="group")
        fig.update_xaxes(title="Risk decile (10 = highest)", tickmode="linear", dtick=1, range=[0.5, 10.5])
        fig.update_yaxes(title="Five-year charge-off frequency")
        chart(fig, key="explorer_deciles", percent_y=True, height=325)
        export(deciles.drop(columns=["order"]), "filtered_risk_deciles.csv", "Download risk deciles")
    with panel("explorer_concentration", right):
        st.subheader("Modeled event concentration")
        dimension = st.selectbox("Group concentration by", list(FILTER_FIELDS), format_func=FILTER_FIELDS.get,
                                 key="explorer_dimension")
        segments = grouped(data, dimension)
        segments["modeled_event_share"] = segments.expected_events / totals.expected_events
        segments["approval_share"] = segments.approved_usd / totals.approved_usd
        visible = segments.nlargest(8, "expected_events").sort_values("expected_events")
        labels = visible.label.map(lambda label: label if len(label) <= 30 else label[:28] + "…")
        fig = go.Figure(go.Bar(
            x=visible.modeled_event_share, y=labels, orientation="h", marker_color=TEAL,
            customdata=list(zip(visible.label, visible.expected_events, visible.predicted_rate, visible.records)),
            hovertemplate="%{customdata[0]}<br>%{x:.1%} of modeled events<br>"
                          "%{customdata[1]:,.1f} modeled events · %{customdata[2]:.2%} mean probability"
                          "<br>%{customdata[3]:,.0f} records<extra></extra>",
        ))
        fig.update_xaxes(title="Share of modeled events in selection")
        fig.update_yaxes(showgrid=False)
        chart(fig, key="explorer_concentration", percent_x=True, height=287)
        export(segments, "filtered_risk_concentration.csv", "Download segment breakdown")

    with panel("explorer_detail"):
        st.subheader("Segment detail")
        st.caption("Modeled events sum frozen probabilities. Small segments can have unstable observed frequencies.")
        st.dataframe(segments[["label", "records", "approved_usd", "observed_rate", "predicted_rate",
                               "expected_events", "modeled_event_share"]].sort_values("expected_events", ascending=False),
                     hide_index=True, width="stretch", column_config={
                         "label": "Segment", "records": st.column_config.NumberColumn("Records", format="localized"),
                         "approved_usd": st.column_config.NumberColumn("Approved principal ($)", format="dollar"),
                         "observed_rate": st.column_config.NumberColumn("Observed", format="percent"),
                         "predicted_rate": st.column_config.NumberColumn("Modeled", format="percent"),
                         "expected_events": st.column_config.NumberColumn("Modeled events", format="%.1f"),
                         "modeled_event_share": st.column_config.NumberColumn("Share of modeled events", format="percent"),
                     })
