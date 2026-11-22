"""Document release provenance, validation, and model-use boundaries."""

import streamlit as st

from creditrisk.paths import ROOT

from .catalog import MODELS
from .lab import METRIC_COLUMNS, comparison
from .ui import cards, export, panel, title

FEATURE_NAMES = {
    "gross_approval": "Gross approved principal", "sba_guaranteed_approval": "SBA-guaranteed approval",
    "initial_interest_rate_pct": "Initial interest rate", "rate_type": "Fixed or variable rate",
    "project_state": "Project state", "naics_code": "NAICS code", "processing_method": "SBA processing method",
    "business_type": "Business type", "business_age": "Business age",
    "collateral_reported": "Reported collateral", "revolving_credit": "Revolving credit flag",
}


def render(key, release):
    from .data import report

    render_evidence(release, report(key, "metrics.csv"), report(key, "cohort_audit.csv"))


def render_evidence(release, metrics, cohort_audit, *, public=False):
    title("Model governance & documentation", "Data provenance, validation evidence and appropriate model use.")
    fit = release["fit"]
    test = comparison(None, "test", metrics=metrics)
    count = int(test.iloc[0].records)
    cards(
        ("Data snapshot", release["snapshot"], "AsOfDate on the source SBA extract."),
        ("Preferred model", MODELS[release["champion"]], "Selected using validation Brier score."),
        ("Holdout population", f"{count:,}", "Eligible FY2018–2019 first disbursements."),
    )
    left, right = st.columns(2)
    with panel("governance_source", left):
        st.subheader("Source and target")
        st.markdown(
            "The U.S. Small Business Administration’s 7(a) FOIA release covers the FY2010–FY2019 "
            "approval vintages in this study. A target of **1** means a recorded SBA charge-off from first "
            "disbursement through the inclusive 60-calendar-month anniversary. The full horizon must "
            "close by the snapshot. Ambiguous histories receive no label. Charge-off is a later "
            "recorded event and the initial default date is unknown."
        )
        st.markdown(
            "Mature EXEMPT records without conflicting evidence are treated as negatives under the "
            "assumption that the release would disclose a qualifying charge-off."
        )
        st.markdown("[SBA 7(a) and 504 FOIA dataset](https://data.sba.gov/dataset/7a-504-foia)")
    with panel("governance_features", right):
        st.subheader("Feature availability and leakage")
        st.markdown("**Frozen model inputs**")
        st.write(", ".join(FEATURE_NAMES.get(name, name.replace("_", " ")) for name in fit["features"]) + ".")
        st.markdown(
            "Servicing outcomes, status, payoff and charge-off dates, loss amounts, identifiers, "
            "and cohort metadata are excluded. Reported term is available for segmentation only "
            "because its snapshot value may incorporate later servicing activity. "
            "Preprocessing was fitted only on training cohorts. This single extract cannot verify "
            "origination-time versions for every otherwise eligible input."
        )

    with panel("governance_validation"):
        st.subheader("Validation strategy and evidence")
        study = st.radio("Validation study", ["retrospective", "horizon_mature"], horizontal=True,
                         format_func={"retrospective": "Retrospective holdout",
                                      "horizon_mature": "Horizon-mature sensitivity"}.get)
        if study == "retrospective":
            st.caption("Fit on FY2010–2015, tune on FY2016, then split FY2017 into calibration and selection. "
                       "Several development labels had yet to mature at the start of FY2018.")
        else:
            st.caption("The sensitivity fit on FY2010, tuned on FY2011, and calibrated and selected on FY2012. "
                       "All development horizons closed before FY2018. Historical extract revisions remain unknown.")
        study_metrics = comparison(None, "test", study, metrics=metrics)
        st.dataframe(study_metrics[["Model", *METRIC_COLUMNS]], column_config=METRIC_COLUMNS,
                     hide_index=True, width="stretch")
        with st.expander("Cohort coverage and label maturity"):
            audit = cohort_audit.loc[cohort_audit.study.eq(study)].drop(columns="study")
            st.dataframe(audit, hide_index=True, width="stretch")
        export(study_metrics, f"governance_{study}_metrics.csv", "Download validation metrics")

    left, right = st.columns(2)
    with panel("governance_use", left):
        st.subheader("Model use and limitations")
        st.markdown(
            "- **Appropriate use:** retrospective portfolio research, segment investigation, and hypothetical sensitivity.\n"
            "- **Decision boundaries:** this research score does not support production underwriting, regulatory PD, "
            "LGD, EAD, reserves, or expected dollar loss.\n"
            "- **Model risk:** calibration changes by vintage. Linked borrowers and servicing revisions cannot be "
            "verified without loan identifiers and point-in-time snapshots."
        )
    with panel("governance_fairness", right):
        st.subheader("Fairness and representativeness")
        st.markdown(
            "- The sample contains eligible funded SBA 7(a) loans. It excludes denied applicants, unfunded approvals, "
            "and records without complete observable follow-up.\n"
            "- Protected-group outcomes were not measured. Geography, industry and other business attributes may proxy "
            "for structural differences. Segment rates alone cannot establish model fairness.\n"
            "- Any proposed deployment needs separate point-in-time, representativeness, subgroup performance, "
            "and fair-lending review."
        )
    with st.expander("Model artifacts and audit documentation"):
        if public:
            st.caption("This mode uses a fixed aggregate release. No borrower records or fitted models are served.")
        else:
            st.code(f"Database SHA-256  {fit['database']['sha256']}\n"
                    f"scikit-learn      {fit['sklearn']}\nXGBoost           {fit['xgboost']}")
        for filename, label in (("modeling_report.md", "Download technical modeling report"),
                                ("target_and_leakage.md", "Download target and leakage assessment")):
            st.download_button(label, (ROOT / "docs" / filename).read_bytes(), file_name=filename,
                               mime="text/markdown", key=filename, on_click="ignore")
