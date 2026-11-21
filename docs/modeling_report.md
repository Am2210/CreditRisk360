# Five-year SBA charge-off modeling

## Decision

Retain **XGBoost** as the retrospective research benchmark for portfolio ranking and logistic regression as the transparent baseline. XGBoost was selected on validation Brier score and led the three models on holdout ROC-AUC, average precision, and Brier score. The improvement over logistic regression is modest. The horizon-mature analysis selected logistic regression, and the retrospective model shows vintage-level calibration drift.

## Population and validation design

The target is unchanged. It measures an SBA-recorded charge-off from first disbursement through the inclusive 60-calendar-month anniversary in the September 30, 2026 release. Eligibility remained **477,797** records with **19,388** events, including the existing treatment of mature `EXEMPT` cases. This is a historical observation of charge-off among funded loans, distinct from the timing of default. [Target definition](target_and_leakage.md)

- **Training** used **254,340** records and 9,863 events from first-disbursement FY2010–2015. The fiscal years are based on disbursement, since approval-year cohorts overlap in actual funding dates.
- **Tuning** used **56,652** FY2016 records. FY2017 was split chronologically into **27,252** calibration records and **29,940** records for selecting the probability mapping, preferred model, cost rules, and decile cutpoints. The untouched **103,136** FY2018–2019 records held **4,631** events (4.49%). Another **6,477** delayed FY2020–2021 disbursements were scored without using their outcomes.
- **Horizon-mature sensitivity.** Only 116,747 primary training records and none of the later validation records had closed horizons by October 1, 2017. In the separate sensitivity, all development horizons had closed before that date. The models fit on FY2010, tuned on FY2011, and used the first and second halves of FY2012 for calibration and selection. Validation selected logistic regression. On the same holdout it scored **0.6591 ROC-AUC, 0.07528 average precision and 0.04236 Brier**. Its mean score was **3.94%** against **4.49%** observed. The older development sample and single 2026 snapshot limit what this comparison can isolate. [Cohort audit](../reports/modeling/cohort_audit.csv)

## Feature and model controls

Use the explicit 11-field modeling allowlist. Approval fiscal year, dates, servicing outcomes, sale status, borrower and lender identifiers, eligibility flags, and the label stay outside the model matrix. **Reported term is excluded.** In training and tuning, 1,067 of 250,873 records with whole-year terms charged off within five years (0.43%), versus 10,001 of 48,209 records whose term was divisible by neither six nor twelve (20.75%). The dictionary does not confirm whether the field retains the original term, and the pattern raises concern about servicing revisions. Term remains available for descriptive analysis. Other candidate fields still need point-in-time confirmation, especially borrower attributes and reported collateral. [Term audit](../reports/modeling/term_leakage_audit.csv)

Median imputation, numeric scaling, missing-category handling, and rare-level grouping were fit on training only. All final primary models used the full training cohort. Four configurations per family varied regularization or tree depth and class weighting. Validation average precision selected the configuration. The final primary winners were unweighted, including the logistic baseline (`C=0.03`), Random Forest (100 trees, depth 17, 25 minimum leaf records), and XGBoost (300 trees, depth 5, learning rate 0.06). The horizon-mature XGBoost selected a positive-class weight equal to the square root of the training prevalence odds for negatives vs positives. No resampling altered validation or test prevalence.

A one-dimensional sigmoid on the raw score logit was fit on the first half of FY2017. Each model kept the mapping only if it improved Brier score in the second half. Random Forest and XGBoost kept sigmoid mappings. Logistic regression kept its native probabilities. All fitting, selection rules, model artifacts, and thresholds were frozen before evaluating held-out outcomes. [Development decisions](../reports/modeling/development_decisions.json)

## Untouched FY2018–2019 results

PR-AUC is reported as average precision (AP). The reference is a constant equal to training prevalence, with test AP **0.04490** and Brier **0.04292**.

- **Logistic regression** — ROC-AUC **0.7017**, AP **0.08736**, Brier **0.04222**. Mean predicted frequency **5.67%**. Calibration slope **1.05**.
- **Random Forest** — ROC-AUC **0.7121**, AP **0.09018**, Brier **0.04191**. Mean predicted frequency **4.88%**. Calibration slope **1.29**.
- **XGBoost** — ROC-AUC **0.7165**, AP **0.09508**, Brier **0.04185**. Mean predicted frequency **5.19%**. Calibration slope **1.12**. The raw test score had marginally lower Brier (**0.04184**) than the frozen sigmoid. The calibration choice was made on validation.

The preferred model's gain over logistic regression was **0.01481 ROC-AUC** and **0.00772 AP**. A paired 200-replicate bootstrap of the 24 origination months gave approximate 95% intervals of **[0.00828, 0.02117]** and **[0.00296, 0.01231]** for those differences and **[-0.00050, -0.00028]** for the Brier difference. These intervals describe the observed test vintages and fitted models. They do not cover future economic cycles or uncertainty from refitting. [Metrics](../reports/modeling/metrics.csv) · [Discrimination](../reports/modeling/discrimination.png) · [Uncertainty](../reports/modeling/test_uncertainty.json)

XGBoost predicted **4.95%** for FY2018 versus **4.80%** observed and **5.47%** for FY2019 versus **4.13%**. The highest validation-defined risk group contained 13,212 test records with **1,428 events**, **11.87% predicted**, and **10.81% observed**. It captured **30.8%** of test events. The bottom group had **0.19% observed**. Cutpoints use validation quantiles, so test groups need not contain equal numbers of records. [Calibration and deciles](../reports/modeling/calibration_and_deciles.png) · [Fiscal-year results](../reports/modeling/test_by_fiscal_year.csv)

## Thresholds and portfolio implications

At the **8%** validation-selected XGBoost threshold, the test set had **2,052 true positives**, **18,837 false positives**, **2,579 false negatives**, and **79,668 true negatives**. Precision was **9.82%** and recall was **44.31%**. The fixed **5%** rule raised recall to **76.14%** and flagged **45.54%** of the test cohort, with precision of **7.51%**. A false positive can consume review capacity or lead to unnecessary escalation. A false negative can miss a chance to monitor or intervene.

The sensitivity analysis assigns **$500 per false positive** and **$2,000, $5,000, or $10,000 per false negative**. For the base case, the 8% validation threshold incurred **$22.314 million** in hypothetical test cost, versus **$23.155 million** for flagging nobody and **$21.974 million** for the prespecified 9.09% probability break-even rule. These fixed per-record penalties illustrate how intervention priorities change the threshold. Actual review cost, intervention benefit, outstanding exposure and realized credit loss are unmeasured. [Confusion matrices](../reports/modeling/confusion_matrices.csv) · [Cost sensitivity](../reports/modeling/cost_sensitivity.csv)

Summing test probabilities gives about **5,355 modeled recorded charge-offs**. California accounted for **11.74%** of the modeled count, NAICS sector 72 for **15.22%**, approvals under $50,000 for **32.90%**, and the reported 61–120 month term band for **71.54%**. Each segmentation is a separate view of the same portfolio. Segment approval dollars remain historical commitments. These results do not estimate regulatory PD, LGD, or EAD. [Risk concentration](../reports/modeling/risk_concentration.csv)

## Explanations and reproducibility

Exact XGBoost Tree SHAP on a reproducible random sample of **2,500** test records ranked **initial interest rate, gross approval, and NAICS code** highest by mean absolute grouped contribution. Summed contributions reconstructed raw model margins to within **0.0000053**. Contributions are on the raw log-odds scale before sigmoid calibration. Correlated features can share attribution, and the explanations do not establish causal effects. [Tree SHAP plot](../reports/modeling/xgboost_tree_shap.png) · [Logistic coefficients](../reports/modeling/logistic_coefficients.csv) · [XGBoost prediction documentation](https://xgboost.readthedocs.io/en/stable/prediction.html)

The local `artifacts/models/` contains fitted preprocessing and estimators, calibration mappings, XGBoost native boosters, the frozen manifest, anonymous explanation examples, and a Parquet score file for all eligible records. Training scores are in-sample and are tagged accordingly. `local_record_id` is a DuckDB row identifier scoped to the fingerprinted database, not a persistent loan identifier. The environment, commands, and safe publication boundary are in the [README](../README.md).
