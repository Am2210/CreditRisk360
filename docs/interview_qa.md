# Interview questions and answers

## 1. What exactly does your model predict?

It estimates an SBA-recorded charge-off from first disbursement through the inclusive 60-calendar-month anniversary. The development population contains funded records whose full window ends by the snapshot. Missing or contradictory histories are unlabeled. Mature EXEMPT records count as negatives when they have no conflicting evidence, under the assumption that a qualifying charge-off would have been disclosed. Charge-off is an observed servicing event that can follow the original default.

## 2. How did you prevent leakage and test whether the validation was realistic?

I excluded outcomes, servicing fields, identifiers, and dates from features. I also excluded reported term after a development-only check found a strong relationship that could reflect servicing changes. All fitted transformations and trees learned from the training cohort. The retrospective split follows first-disbursement fiscal year. Some training and validation labels had yet to mature at the start of the holdout, so I ran a separate study that censored development to windows already closed by that date. That sensitivity chose logistic regression and achieved 0.6591 ROC-AUC. Both use a single later extract, so contemporaneous data availability is still unverified.

## 3. Why did you select XGBoost, and what does its performance tell you?

XGBoost had the lowest Brier score on the retrospective selection cohort. In the FY2018–2019 holdout it achieved 0.7165 ROC-AUC, 0.09508 average precision, and 0.04185 Brier. The highest risk group captured 30.8% of charge-offs, but mean probabilities overpredicted the overall rate. I would use the ranking to study prioritization and require newer, point-in-time validation before relying on probability levels. Logistic regression remains a transparent benchmark and won the horizon-mature selection.

## 4. How would the score affect a credit-review queue?

At the 8% validation-selected XGBoost threshold, 20.25% of holdout records would be flagged. About 9.82% of flags were actual events, and the rule caught 44.31% of observed charge-offs. Dropping the threshold to 5% raised recall to 76.14% while flagging 45.54% of records. The trade-off is coverage versus false positives and review capacity. The project's per-record cost assumptions are hypothetical.

## 5. How does the stress test work, and what data would you ask for next?

It multiplies each probability by the scenario factor, caps each result at 100%, and averages the adjusted probabilities using gross approvals as weights. Scaling the historical mix to $10 million preserves those weights. To estimate dollar losses I would need monthly balances, utilization at default, default timing, recoveries, and defensible relationships between economic shocks and credit performance.
