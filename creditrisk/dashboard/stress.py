"""Hypothetical scenario sensitivity on an approved-principal proxy basis."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .catalog import FILTER_FIELDS, MODELS
from .ui import BLUE, GOLD, TEAL, cards, chart, export, filters, grouped, money, panel, pct, title

SCENARIOS = {"baseline": ("Baseline", BLUE), "moderate": ("Moderate stress", TEAL), "severe": ("Severe stress", GOLD)}
ILLUSTRATIVE_AMOUNT = 10_000_000
WEIGHT_HELP = "Sum of approved principal × stressed probability divided by total approved principal."


def render(key, release):
    from .data import aggregates

    model = release["champion"]
    title("Credit stress testing", f"Apply hypothetical probability shocks to the frozen {MODELS[model]} scores.")
    controls = st.columns([1.65, 1, 1, 1.3])
    basis = controls[0].selectbox("Portfolio basis", ["Illustrative $10 million", "Historical approved principal"])
    moderate = controls[1].number_input("Moderate multiplier", min_value=1.0, max_value=100.0, value=1.25,
                                        step=0.05, format="%.2f")
    severe = controls[2].number_input("Severe multiplier", min_value=1.0, max_value=100.0, value=1.75,
                                      step=0.05, format="%.2f")
    dimensions = ["industry", "state", "size", "term", "vintage", "collateral"]
    dimension = controls[3].selectbox("Segment comparison", dimensions, format_func=FILTER_FIELDS.get,
                                     key="stress_dimension")
    if severe < moderate:
        st.warning("Set the severe multiplier at or above the moderate multiplier to run the comparison.")
        return
    with st.expander("Choose cohort and segment filters"):
        scope = filters(key, model, "stress")
    data = aggregates(key, scope, ("portfolio", dimension), model, stress=(moderate, severe))
    if data.empty:
        st.info("No records match these filters. Change the cohort or clear a filter to run a scenario.")
        return
    totals = grouped(data, "portfolio").iloc[0]
    if totals.approved_usd <= 0:
        st.info("An approved-principal-weighted indicator requires positive approved principal in the selection.")
        return
    illustrative = basis.startswith("Illustrative")
    base_amount = ILLUSTRATIVE_AMOUNT if illustrative else totals.approved_usd
    scale = base_amount / totals.approved_usd
    cards(
        ("Portfolio proxy basis", money(base_amount), "Historical approved principal, optionally rescaled proportionally."),
        ("Baseline indicator", pct(totals.baseline), WEIGHT_HELP),
        ("Moderate indicator", pct(totals.moderate), WEIGHT_HELP),
        ("Severe indicator", pct(totals.severe), WEIGHT_HELP),
    )
    if illustrative:
        st.caption(f"The illustrative portfolio preserves the approved-principal weights of {totals.records:,.0f} selected historical records.")
    else:
        st.caption(f"Historical proxy uses the gross approvals of {totals.records:,.0f} selected records.")

    scenario_rows = pd.DataFrame([
        {"scenario": label, "multiplier": factor, "weighted_event_indicator": totals[name],
         "uplift_basis_points": (totals[name] - totals.baseline) * 10_000,
         "approved_principal_basis_usd": base_amount}
        for (name, (label, _)), factor in zip(SCENARIOS.items(), (1.0, moderate, severe))
    ])
    segments = grouped(data, dimension)
    segments["approval_share"] = segments.approved_usd / totals.approved_usd
    segments["approved_principal_proxy_usd"] = segments.approved_usd * scale
    segments["severe_uplift_bps"] = (segments.severe - segments.baseline) * 10_000
    largest = segments.nlargest(8, "approved_usd").sort_values("approved_usd")
    labels = largest.label.map(lambda label: label if len(label) <= 29 else label[:27] + "…")

    left, right = st.columns([1, 1.35])
    with panel("stress_scenarios", left):
        st.subheader("Portfolio scenario comparison")
        fig = go.Figure(go.Bar(
            x=scenario_rows.scenario, y=scenario_rows.weighted_event_indicator,
            marker_color=[color for _, color in SCENARIOS.values()],
            text=[pct(value) for value in scenario_rows.weighted_event_indicator], textposition="outside",
            customdata=scenario_rows.uplift_basis_points,
            hovertemplate="%{x}<br>%{y:.2%}<br>%{customdata:+.0f} bps vs baseline<extra></extra>",
        ))
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(title="Weighted charge-off indicator", range=[0, min(1.12, totals.severe * 1.24 + 0.005)])
        chart(fig, key="stress_scenarios", percent_y=True, height=325)
        export(scenario_rows.assign(portfolio_basis=basis, cohort=scope.cohort), "stress_scenarios.csv",
               "Download scenario comparison")
    with panel("stress_segments", right):
        st.subheader("Segment sensitivity")
        st.caption("Top eight segments by approved-principal proxy")
        fig = go.Figure()
        for name, (label, color) in SCENARIOS.items():
            fig.add_bar(y=labels, x=largest[name], name=label, orientation="h", marker_color=color,
                        customdata=list(zip(largest.label, largest.approval_share)),
                        hovertemplate="%{customdata[0]}<br>%{x:.2%} weighted indicator"
                                      "<br>%{customdata[1]:.1%} of proxy basis<extra>%{fullData.name}</extra>")
        fig.update_layout(barmode="group")
        fig.update_xaxes(title="Weighted charge-off indicator")
        fig.update_yaxes(showgrid=False)
        chart(fig, key="stress_segments", percent_x=True, height=385)

    with panel("stress_concentration"):
        st.subheader("Portfolio concentration")
        fig = go.Figure(go.Bar(
            y=labels, x=largest.approval_share, orientation="h", marker_color=BLUE,
            customdata=list(zip(largest.label, largest.approved_principal_proxy_usd)),
            hovertemplate="%{customdata[0]}<br>%{x:.1%} of proxy basis"
                          "<br>$%{customdata[1]:,.0f} proxy basis<extra></extra>",
        ))
        fig.update_xaxes(title="Share of approved-principal proxy")
        fig.update_yaxes(showgrid=False)
        chart(fig, key="stress_concentration", percent_x=True, height=275)
        export(segments.assign(portfolio_basis=basis, cohort=scope.cohort,
                               moderate_multiplier=moderate, severe_multiplier=severe),
               "stress_segment_sensitivity.csv", "Download segment sensitivity")
    st.warning(
        "Illustrative sensitivity only. Each loan’s probability is multiplied and capped at 100% before weighting. "
        "The multipliers are hypothetical and carry no macroeconomic calibration. The indicator uses approved "
        "principal as a proxy. The release provides no current balances, exposure at default, loss severity, or "
        "recoveries, so the result cannot be interpreted as expected dollar loss."
    )
