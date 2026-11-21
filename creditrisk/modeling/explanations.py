"""Explain the fitted XGBoost trees with exact Tree SHAP contributions."""

import numpy as np
import pandas as pd
from xgboost import DMatrix

from .cohorts import CATEGORICAL, FEATURES, NUMERIC, features
from .estimators import SEED, WORKERS


def explain(model, test, count=2500):
    # Explain a reproducible simple random sample of the untouched cohort.
    sample = test.sample(n=min(count, len(test)), random_state=SEED)
    pre = model.preprocessing
    matrix = DMatrix(pre.transform(features(sample)), nthread=WORKERS)
    booster = model.estimator.get_booster()
    contributions = booster.predict(matrix, pred_contribs=True)
    margin = booster.predict(matrix, output_margin=True)
    error = np.max(np.abs(contributions.sum(axis=1) - margin))
    if error > 1e-4:
        raise ValueError(f"Tree SHAP additivity failed: {error}")
    explanations = {}
    for column, name in enumerate(pre.get_feature_names_out()):
        branch, encoded = name.split("__", maxsplit=1)
        if branch == "numeric":
            feature = encoded.removeprefix("missingindicator_")
            assert feature in NUMERIC
        else:
            feature, = [field for field in CATEGORICAL if encoded.startswith(field + "_")]
        explanations.setdefault(feature, []).append(column)
    if set(explanations) != set(FEATURES):
        raise ValueError("Transformed features did not map back to all source features.")
    grouped = pd.DataFrame({field: contributions[:, columns].sum(axis=1)
                            for field, columns in explanations.items()})
    importance = pd.DataFrame({
        "feature": grouped.columns,
        "mean_abs_shap_margin": grouped.abs().mean().to_numpy(),
        "mean_signed_shap_margin": grouped.mean().to_numpy(),
        "p05_shap_margin": grouped.quantile(0.05).to_numpy(),
        "p95_shap_margin": grouped.quantile(0.95).to_numpy(),
    }).sort_values("mean_abs_shap_margin", ascending=False)
    examples = []
    scores = model.predict(sample)
    order = np.argsort(scores)
    for name, index in {"low": order[len(order) // 10], "median": order[len(order) // 2],
                        "high": order[9 * len(order) // 10]}.items():
        for feature, value in grouped.iloc[index].items():
            examples.append({"example": name, "feature": feature, "shap_margin": value,
                             "base_margin": float(contributions[index, -1]), "raw_margin": float(margin[index]),
                             "reported_probability": float(scores[index])})
    return importance, pd.DataFrame(examples), {"sample_records": len(sample), "max_additivity_error": float(error)}
