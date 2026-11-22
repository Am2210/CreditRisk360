"""Interactive validation of the three frozen probability models."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .catalog import MODELS
from .ui import BLUE, GOLD, MODEL_COLORS, SLATE, TEAL, cards, chart, export, panel, pct, title

METRIC_COLUMNS = {
    "roc_auc": st.column_config.NumberColumn("ROC-AUC", format="%.4f", help="Ranking across positives and negatives."),
    "pr_auc_average_precision": st.column_config.NumberColumn(
        "Average precision", format="%.4f", help="Precision–recall performance summarized by average precision."
    ),
    "brier": st.column_config.NumberColumn("Brier score", format="%.5f", help="Mean squared probability error. Lower is better."),
    "predicted_rate": st.column_config.NumberColumn("Mean predicted", format="percent"),
    "observed_rate": st.column_config.NumberColumn("Observed frequency", format="percent"),
}


def comparison(key, cohort, study="retrospective", *, metrics=None):
    if metrics is None:
        from .data import report
        metrics = report(key, "metrics.csv")
    chosen = metrics.loc[
        metrics.study.eq(study) & metrics.cohort.eq(cohort) & metrics.variant.isin(["selected", "reference"])
    ].copy()
    chosen["Model"] = chosen.model.map({**MODELS, "training_prevalence": "Training prevalence reference"})
    return chosen


def curves(data, prevalence):
    metrics = {
        "roc": ("Receiver operating characteristic", "False positive rate", "True positive rate"),
        "pr": ("Precision–recall", "Recall", "Precision"),
    }
    for column, (kind, (label, x_title, y_title)) in zip(st.columns(2), metrics.items()):
        with panel(f"lab_{kind}", column):
            st.subheader(label)
            fig = go.Figure()
            for model, values in data.items():
                x, y = values[kind]
                fig.add_scatter(x=x, y=y, mode="lines", name=MODELS[model],
                                line={"color": MODEL_COLORS[model], "width": 2.6},
                                hovertemplate="%{x:.1%} · %{y:.1%}<extra>%{fullData.name}</extra>")
            reference = [0, 1] if kind == "roc" else [prevalence, prevalence]
            fig.add_scatter(x=[0, 1], y=reference, mode="lines", name="Reference",
                            line={"color": SLATE, "dash": "dash", "width": 1.3})
            fig.update_xaxes(title=x_title, range=[0, 1])
            fig.update_yaxes(title=y_title, range=[0, 1])
            if kind == "pr":
                fig.update_yaxes(type="linear", tickformat=".0%")
            chart(fig, key=f"lab_{kind}", percent_x=True, percent_y=True, height=310)


def calibration(key, cohort, model):
    from .data import report

    bins = report(key, "reliability.csv")
    bins = bins.loc[
        bins.study.eq("retrospective") & bins.cohort.eq(cohort)
        & bins.model.eq(model) & bins.records.ge(25)
    ]
    extent = max(0.10, float(bins[["predicted_rate", "observed_rate"]].max().max()) * 1.08)
    fig = go.Figure(go.Scatter(x=[0, extent], y=[0, extent], mode="lines", name="Perfect calibration",
                               line={"color": SLATE, "dash": "dash"}))
    for variant, label, color in (("raw", "Raw probability", BLUE), ("selected", "Selected probability", TEAL)):
        rows = bins.loc[bins.variant.eq(variant)]
        fig.add_scatter(x=rows.predicted_rate, y=rows.observed_rate, mode="lines+markers", name=label,
                        line={"color": color}, customdata=rows.records,
                        hovertemplate="%{x:.2%} predicted · %{y:.2%} observed<br>%{customdata:,} records"
                                      "<extra>%{fullData.name}</extra>")
    fig.update_xaxes(title="Mean predicted probability", range=[0, extent])
    fig.update_yaxes(title="Observed frequency", range=[0, extent])
    chart(fig, key="lab_calibration", percent_x=True, percent_y=True)


def distribution(key, cohort, model, threshold):
    import numpy as np
    from .data import model_scores

    saved = model_scores(key, cohort)
    edges = np.linspace(0, max(0.05, float(saved[model].max())), 30)
    fig = go.Figure()
    for outcome, color, label in ((0, BLUE, "No observed charge-off"), (1, GOLD, "Observed charge-off")):
        counts, _ = np.histogram(saved.loc[saved.outcome.eq(outcome), model], bins=edges)
        fig.add_bar(x=(edges[1:] + edges[:-1]) / 2, y=counts / counts.sum(), name=label,
                    width=np.diff(edges), marker_color=color, opacity=0.74,
                    hovertemplate="%{x:.2%} score · %{y:.2%} of outcome group<extra>%{fullData.name}</extra>")
    fig.update_layout(barmode="overlay")
    fig.add_vline(x=threshold, line_color=TEAL, line_dash="dot")
    fig.update_xaxes(title="Predicted five-year probability")
    fig.update_yaxes(title="Share within outcome group")
    chart(fig, key="lab_distribution", percent_x=True, percent_y=True)


def render(key, release):
    from .data import discrimination, model_diagnostics, report

    title("Credit risk model lab", "Compare frozen models, calibration and decision thresholds on saved scores.")
    selectors = st.columns([1, 1, 1.4])
    models = list(MODELS)
    model = selectors[0].selectbox("Model", models, index=models.index(release["champion"]), format_func=MODELS.get)
    cohort = selectors[1].selectbox("Evaluation cohort", ("test", "selection"),
                                    format_func={"test": "FY2018–2019 holdout", "selection": "FY2017 selection"}.get)
    rule = release["fit"]["studies"]["retrospective"]["thresholds"][model]["base"]["validation_threshold"]
    threshold = selectors[2].slider(
        "Charge-off probability threshold (%)", 0.0, 100.0, round(min(rule, 1) * 100, 1), step=0.1,
        key=f"lab_threshold_{model}", help="Records with probability at or above the threshold are flagged.",
    ) / 100
    rows = comparison(key, cohort)
    selected = rows.loc[rows.model.eq(model)].iloc[0]
    cards(
        ("ROC-AUC", f"{selected.roc_auc:.4f}", "Ranking performance across event and non-event records."),
        ("Average precision", f"{selected.pr_auc_average_precision:.4f}", "Precision–recall summary for the observed event."),
        ("Brier score", f"{selected.brier:.5f}", "Mean squared probability error. Lower is better."),
        ("Mean predicted", pct(selected.predicted_rate), f"Observed frequency in this cohort was {pct(selected.observed_rate)}."),
    )
    with panel("lab_comparison"):
        st.subheader("Model comparison")
        st.dataframe(rows[["Model", *METRIC_COLUMNS]], column_config=METRIC_COLUMNS, hide_index=True, width="stretch")
        export(rows, "model_comparison.csv", "Download comparison")
    curves(discrimination(key, cohort), float(selected.observed_rate))
    left, right = st.columns(2)
    with panel("lab_calibration", left):
        st.subheader("Probability calibration")
        st.caption("Compare predicted and observed rates in probability bins with at least 25 records")
        calibration(key, cohort, model)
    with panel("lab_distribution", right):
        st.subheader("Predicted risk distribution")
        st.caption("Each outcome group is normalized separately. The vertical line marks the selected threshold.")
        distribution(key, cohort, model, threshold)
    diag = model_diagnostics(key, cohort, model, threshold)
    with panel("lab_confusion"):
        st.subheader(f"Confusion matrix at {threshold:.1%}")
        left, right = st.columns([1, 1.15])
        with left:
            fig = go.Figure(go.Heatmap(
                z=[[diag["tn"], diag["fp"]], [diag["fn"], diag["tp"]]],
                x=["Clear", "Flag"], y=["No charge-off", "Charge-off"], texttemplate="%{z:,}",
                colorscale=[[0, "#e4eff6"], [1, "#34658b"]], showscale=False,
                hovertemplate="Actual %{y} · Decision %{x}<br>%{z:,} records<extra></extra>",
            ))
            fig.update_xaxes(title="Decision")
            fig.update_yaxes(title="Observed outcome", autorange="reversed")
            chart(fig, key="lab_matrix", height=215)
        with right:
            st.metric("Precision", pct(diag["precision"]), help="Share of flagged records that charged off.")
            st.metric("Recall", pct(diag["recall"]), help="Share of records that charged off and were flagged.")
            st.caption(f"{pct(diag['flagged_rate'])} of records flagged. Precision is undefined when no records are flagged.")
            export(pd.DataFrame([{"model": MODELS[model], "cohort": cohort, **diag}]),
                   "threshold_results.csv", "Download threshold results")

    with panel("lab_shap"):
        st.subheader("XGBoost feature explanations")
        sample = release["summary"]["explanation"]["sample_records"]
        st.caption(f"Tree SHAP on {sample:,} holdout records. Contributions describe raw log-odds before calibration.")
        shap = report(key, "tree_shap_importance.csv").sort_values("mean_abs_shap_margin")
        fig = go.Figure(go.Bar(
            x=shap.mean_abs_shap_margin, y=shap.feature.str.replace("_", " ").str.capitalize(),
            orientation="h", marker_color=TEAL,
            hovertemplate="%{y}<br>%{x:.3f} mean absolute contribution<extra></extra>",
        ))
        fig.update_xaxes(title="Mean absolute contribution (log-odds)")
        fig.update_yaxes(showgrid=False)
        chart(fig, key="lab_shap", height=345)
        export(shap, "tree_shap_importance.csv", "Download feature contributions")
