"""Compute threshold statistics and freeze decision rules on validation only."""

import numpy as np
from sklearn.metrics import confusion_matrix

SCENARIOS = {
    "low_miss_cost": (500, 2000),
    "base": (500, 5000),
    "high_miss_cost": (500, 10000),
}
THRESHOLD_GRID = np.unique(np.r_[0, np.arange(0.005, 0.305, 0.005), 1.000001])


def confusion(target, probabilities, threshold):
    tn, fp, fn, tp = confusion_matrix(target, probabilities >= threshold, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold), "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "flagged_rate": float((tp + fp) / len(target)),
        "precision": float(tp / (tp + fp)) if tp + fp else None,
        "recall": float(tp / (tp + fn)) if tp + fn else None,
    }


def costs(target, probabilities, threshold, scenario):
    fp_cost, fn_cost = SCENARIOS[scenario]
    counts = confusion(target, probabilities, threshold)
    total = counts["fp"] * fp_cost + counts["fn"] * fn_cost
    return {"scenario": scenario, "fp_cost_usd": fp_cost, "fn_cost_usd": fn_cost,
            **counts, "total_cost_usd": total, "cost_per_record_usd": total / len(target)}


def freeze_thresholds(target, probabilities):
    rules = {}
    for scenario, (fp_cost, fn_cost) in SCENARIOS.items():
        comparisons = [costs(target, probabilities, value, scenario) for value in THRESHOLD_GRID]
        # If costs tie, use the higher threshold to limit review volume.
        best = min(comparisons, key=lambda row: (row["total_cost_usd"], -row["threshold"]))
        rules[scenario] = {"bayes_threshold": fp_cost / (fp_cost + fn_cost),
                           "validation_threshold": best["threshold"]}
    return rules


def fit_deciles(scores):
    return np.quantile(scores, np.arange(1, 10) / 10).tolist()


def risk_decile(scores, cutpoints):
    # Equal scores stay together, so exact bucket sizes can vary on new cohorts.
    return np.searchsorted(cutpoints, scores, side="right") + 1
