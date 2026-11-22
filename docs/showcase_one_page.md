# CreditRisk 360

**Explainable Credit Risk Modeling & Portfolio Stress Analytics**

[Launch the live dashboard](https://creditrisk360-eveittxvutuwaig2upqksd.streamlit.app/)

## Why it matters

A small-business portfolio can grow while risk builds in particular vintages, industries, or loan-size segments. Monitoring teams need a consistent way to rank accounts for review, see where charge-offs concentrate, and understand how much confidence to place in a modeled probability.

## What I built

I turned the September 30, 2026 SBA 7(a) FOIA snapshot into a reproducible DuckDB and Python workflow and a five-page Streamlit dashboard. The pipeline checked **545,751** FY2010–FY2019 approval records and produced **477,797** eligible records with **$180.04 billion** in historical gross approvals. **19,388** records had an SBA-recorded charge-off within five years of first disbursement, an observed frequency of **4.06%**. SQL handles data quality, label construction, and portfolio aggregation. The dashboard reads frozen predictions and supports segment monitoring and hypothetical stress testing.

## Why these models

Logistic regression provides an interpretable baseline. Random Forest tests whether nonlinear relationships improve results. XGBoost tests whether sequentially fitted trees rank risk better. I learned preprocessing on training data, tuned and calibrated on later cohorts, and reserved FY2018–2019 first disbursements for final retrospective evaluation. I excluded servicing outcomes and reported term because the snapshot does not establish that term was recorded as of origination.

## What the results mean

XGBoost achieved **0.7165 ROC-AUC** and **0.09508 average precision** against a **4.49%** holdout event rate. The highest validation-defined risk group contained **30.8%** of holdout charge-offs. Those results show a useful ranking signal for review prioritization. Predicted frequency averaged **5.19%** against **4.49%** observed, and the horizon-mature study selected logistic regression at **0.6591 ROC-AUC**. I would treat both as research results until tested with genuinely point-in-time data.

An illustrative **$10 million** portfolio gave approved-principal-weighted event indicators of **2.32%, 2.90%, and 4.06%** under baseline, moderate, and severe scenarios. These scenarios measure sensitivity to probability shocks. Realized loss requires exposure and severity data.

## What I would improve

With stable loan and borrower IDs, monthly balances, payment history, delinquency and default dates, charge-offs, recoveries, and archived underwriting inputs, I would separate default timing from charge-off timing. I would validate label availability against historical snapshots, isolate linked borrowers across folds, measure calibration and fairness by vintage and subgroup, and backtest balance- and recovery-based stress assumptions.

[Technical report](modeling_report.md) · [Interview questions](interview_qa.md) · [Verified run](release_validation.md)
