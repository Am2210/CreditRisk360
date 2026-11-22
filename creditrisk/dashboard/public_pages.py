"""Render the five dashboard sections using only approved aggregates."""

import plotly.graph_objects as go
import streamlit as st

from . import governance, lab, overview
from .catalog import FILTER_FIELDS, MODELS
from .ui import BLUE, GOLD, SLATE, TEAL, cards, chart, export, grouped, money, panel, pct, title


def executive(tables):
    overview.render_summary(tables["overview.csv"])


def model_lab(manifest, tables):
    title("Credit risk model lab", "Frozen FY2018–2019 holdout results and aggregate validation charts.")
    models = list(MODELS)
    model = st.selectbox("Model", models, index=models.index(manifest["champion"]), format_func=MODELS.get)
    comparison = lab.comparison(None, "test", metrics=tables["metrics.csv"])
    selected = comparison.loc[comparison.model.eq(model)].iloc[0]
    cards(
        ("ROC-AUC", f"{selected.roc_auc:.4f}", "Ranking performance across events and non-events."),
        ("Average precision", f"{selected.pr_auc_average_precision:.4f}", "Holdout precision–recall summary."),
        ("Brier score", f"{selected.brier:.5f}", "Mean squared probability error. Lower is better."),
        ("Mean predicted", pct(selected.predicted_rate), f"Observed frequency was {pct(selected.observed_rate)}."),
    )
    with panel("public_comparison"):
        st.subheader("Model comparison")
        st.dataframe(comparison[["Model", *lab.METRIC_COLUMNS]], column_config=lab.METRIC_COLUMNS,
                     hide_index=True, width="stretch")
        export(comparison, "public_model_comparison.csv", "Download model comparison")
    st.caption("The charts use pooled probability bands. The comparison table retains the original full-score metrics.")
    points = {name: {"roc": (rows.false_positive_rate, rows.recall), "pr": (rows.recall, rows.precision)}
              for name, rows in tables["curves.csv"].groupby("model")}
    lab.curves(points, float(selected.observed_rate))

    left, right = st.columns(2)
    with panel("public_calibration", left):
        st.subheader("Probability calibration")
        bins = tables["calibration.csv"].query("model == @model")
        extent = max(bins.predicted_rate.max(), bins.observed_rate.max()) * 1.12
        fig = go.Figure(go.Scatter(x=[0, extent], y=[0, extent], mode="lines", name="Perfect calibration",
                                   line={"color": SLATE, "dash": "dash"}))
        fig.add_scatter(x=bins.predicted_rate, y=bins.observed_rate, mode="lines+markers",
                        name=MODELS[model], line={"color": TEAL}, customdata=bins.records,
                        hovertemplate="%{x:.2%} predicted · %{y:.2%} observed<br>%{customdata:,} records<extra></extra>")
        fig.update_xaxes(title="Mean modeled probability", range=[0, extent])
        fig.update_yaxes(title="Observed frequency", range=[0, extent])
        chart(fig, key="public_calibration_plot", percent_x=True, percent_y=True)
    with panel("public_threshold", right):
        row = tables["threshold.csv"].query("model == @model").iloc[0]
        st.subheader(f"Confusion matrix at {row.threshold:.0%}")
        fig = go.Figure(go.Heatmap(
            z=[[row.tn, row.fp], [row.fn, row.tp]], x=["Clear", "Flag"], y=["No charge-off", "Charge-off"],
            texttemplate="%{z:,}", colorscale=[[0, "#e4eff6"], [1, "#34658b"]], showscale=False,
        ))
        fig.update_yaxes(autorange="reversed")
        chart(fig, key="public_threshold_plot", height=236)
        st.caption(f"Precision {pct(row.tp / (row.tp + row.fp))} · Recall {pct(row.tp / (row.tp + row.fn))}. "
                   "The public view uses a fixed threshold.")
    with panel("public_explanations"):
        st.subheader("XGBoost feature explanations")
        st.caption(f"Grouped Tree SHAP from {manifest['shap_sample_records']:,} holdout records, in raw log-odds.")
        shap = tables["tree_shap_importance.csv"].sort_values("mean_abs_shap_margin")
        fig = go.Figure(go.Bar(x=shap.mean_abs_shap_margin, y=shap.feature.str.replace("_", " "),
                               orientation="h", marker_color=TEAL))
        fig.update_xaxes(title="Mean absolute contribution (raw log-odds)")
        chart(fig, key="public_shap", height=350)


def risk_explorer(tables):
    title("Portfolio risk explorer", "Compare observed and modeled risk within the fixed FY2018–2019 holdout.")
    data = tables["explorer.csv"]
    st.caption("Choose one breakdown at a time. Sparse segments are pooled, and filters cannot be combined.")
    with panel("public_risk_groups"):
        st.subheader("Observed and modeled risk groups")
        deciles = grouped(data, "decile").sort_values("predicted_rate")
        fig = go.Figure()
        for column, label, color in (("observed_rate", "Observed", BLUE), ("predicted_rate", "Modeled", TEAL)):
            fig.add_bar(x=deciles.segment, y=deciles[column], name=label, marker_color=color,
                        hovertemplate="Risk group %{x} · %{y:.2%}<extra>%{fullData.name}</extra>")
        fig.update_layout(barmode="group")
        fig.update_xaxes(type="category", title="Validation-defined risk group")
        fig.update_yaxes(title="Five-year charge-off rate")
        chart(fig, key="public_risk_group_chart", percent_y=True)
        export(deciles.drop(columns="label"), "public_risk_groups.csv", "Download risk groups")
    with panel("public_risk_segments"):
        st.subheader("Modeled event concentration")
        dimension = st.selectbox("Breakdown", ("industry", "state", "size", "term"), format_func=FILTER_FIELDS.get)
        segments = grouped(data, dimension)
        segment = st.selectbox("Published segment", ["All published segments", *segments.label])
        visible = segments if segment == "All published segments" else segments.loc[segments.label.eq(segment)]
        ordered = visible.nlargest(10, "expected_events").sort_values("expected_events")
        fig = go.Figure(go.Bar(x=ordered.modeled_event_share, y=ordered.label, orientation="h", marker_color=TEAL,
                               hovertemplate="%{y}<br>%{x:.2%} of modeled holdout events<extra></extra>"))
        fig.update_xaxes(title="Share of modeled holdout charge-offs")
        chart(fig, key="public_concentration", percent_x=True)
        st.dataframe(visible[["label", "records", "approved_usd", "observed_rate", "predicted_rate"]],
                     hide_index=True, width="stretch", column_config={
                         "label": "Segment", "records": "Records",
                         "approved_usd": st.column_config.NumberColumn("Historical approvals", format="dollar"),
                         "observed_rate": st.column_config.NumberColumn("Observed", format="percent"),
                         "predicted_rate": st.column_config.NumberColumn("Modeled", format="percent"),
                     })
        export(visible.drop(columns="label"), "public_segment_summary.csv", "Download segment summary")


def stress_testing(tables):
    title("Credit stress testing", "Three fixed probability shocks on the FY2018–2019 holdout mix.")
    rows = tables["stress.csv"]
    st.caption(f"The illustrative portfolio uses {rows.iloc[0].record_count:,.0f} holdout records. "
               "Custom shocks and segment-level stress are available in the full local app.")
    cards(
        ("Portfolio proxy basis", money(rows.iloc[0].proxy_basis_usd), "Gross approved principal scaled proportionally."),
        *((row.scenario, pct(row.weighted_event_indicator), f"{row.multiplier:g}× frozen probability, capped before weighting.")
          for row in rows.itertuples()),
    )
    with panel("public_stress"):
        st.subheader("Portfolio scenario comparison")
        fig = go.Figure(go.Bar(
            x=rows.scenario, y=rows.weighted_event_indicator, marker_color=[BLUE, TEAL, GOLD],
            text=rows.weighted_event_indicator.map(pct), textposition="outside", customdata=rows.multiplier,
            hovertemplate="%{x}<br>%{y:.2%} weighted indicator<br>%{customdata:g}× multiplier<extra></extra>",
        ))
        fig.update_yaxes(title="Approved-principal-weighted charge-off indicator",
                         range=[0, rows.weighted_event_indicator.max() * 1.2])
        chart(fig, key="public_scenarios", percent_y=True, height=335)
        export(rows, "public_stress_scenarios.csv", "Download stress assumptions and results")
    st.warning("Hypothetical probability shocks. Each adjusted probability is capped at 100% before "
               "weighting by approved principal. Current balances, EAD, loss severity, and recoveries are unavailable, "
               "so the indicator cannot be interpreted as expected dollar loss.")


def model_governance(manifest, tables):
    governance.render_evidence(manifest, tables["metrics.csv"], tables["cohort_audit.csv"], public=True)
