"""Discrimination, probability calibration, and portfolio summaries."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from .estimators import SEED, probability_logit


def performance(target, scores):
    target, scores = np.asarray(target), np.asarray(scores)
    if target.shape != scores.shape or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError("Expected one finite probability in [0, 1] per outcome.")
    return {
        "roc_auc": roc_auc_score(target, scores),
        "pr_auc_average_precision": average_precision_score(target, scores),
        "brier": brier_score_loss(target, scores),
    }


def reliability(target, scores):
    # Left-closed 5-point bins; an exact score of 1 belongs to the final bin.
    indices = np.minimum(np.floor(np.asarray(scores) * 20).astype(int), 19)
    records = []
    for index in np.unique(indices):
        mask = indices == index
        records.append({"bin_low": index / 20, "bin_high": (index + 1) / 20, "records": int(mask.sum()),
                        "predicted_rate": float(np.mean(scores[mask])),
                        "observed_rate": float(np.mean(target[mask]))})
    return records


def calibration_summary(target, scores):
    fit = LogisticRegression(C=1000).fit(probability_logit(scores).reshape(-1, 1), target)
    bins = reliability(target, scores)
    return {
        "records": len(target), "events": int(target.sum()),
        "observed_rate": float(target.mean()), "predicted_rate": float(scores.mean()),
        "calibration_intercept": float(fit.intercept_[0]),
        "calibration_slope": float(fit.coef_[0, 0]),
        "ece_5pp": sum(row["records"] * abs(row["observed_rate"] - row["predicted_rate"])
                       for row in bins) / len(target),
    }


def bootstrap_comparison(target, champion, baseline, dates, replicates=200):
    """Pair resamples at the origination-month level to retain within-month grouping."""
    month = dates.dt.strftime("%Y-%m").to_numpy()
    blocks = [np.flatnonzero(month == value) for value in np.unique(month)]
    rng = np.random.default_rng(SEED)
    samples = []
    for _ in range(replicates):
        indices = np.concatenate([blocks[i] for i in rng.integers(len(blocks), size=len(blocks))])
        first = performance(target[indices], champion[indices])
        second = performance(target[indices], baseline[indices])
        samples.append({**{f"champion_{key}": value for key, value in first.items()},
                        **{f"difference_{key}": first[key] - second[key] for key in first}})
    limits = pd.DataFrame(samples).quantile([0.025, 0.975])
    return {"blocks": len(blocks), "replicates": replicates,
            "percentile_intervals": {key: list(values) for key, values in limits.items()}}


def summarize_groups(frame, keys, *, include_observed=True):
    grouped = frame.groupby(keys, observed=True, dropna=False)
    result = grouped.agg(
        records=("probability", "size"), predicted_rate=("probability", "mean"),
        expected_recorded_events=("probability", "sum"), gross_approval_usd=("gross_approval", "sum"),
    )
    result["predicted_event_share"] = result["expected_recorded_events"] / result["expected_recorded_events"].sum()
    if include_observed:
        result["observed_events"] = grouped["charge_off_60m"].sum()
        result["observed_rate"] = grouped["charge_off_60m"].mean()
    return result.reset_index()
