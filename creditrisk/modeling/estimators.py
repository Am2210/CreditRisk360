"""Fit candidates on development cohorts and freeze a probability mapping."""

from dataclasses import dataclass

import numpy as np
from scipy.special import logit
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

from .cohorts import CATEGORICAL, NUMERIC, TARGET, features

SEED = 360
WORKERS = 6
GRIDS = {
    "logistic": [
        {"C": strength, "class_weight": weight}
        for strength in (0.03, 1.0) for weight in (None, "balanced")
    ],
    "random_forest": [
        {"max_depth": depth, "min_samples_leaf": leaf, "class_weight": weight}
        for depth, leaf in ((11, 45), (17, 25))
        for weight in (None, "balanced_subsample")
    ],
    "xgboost": [
        {"max_depth": depth, "scale_pos_weight": weight}
        for depth in (3, 5) for weight in ("unweighted", "sqrt_ratio")
    ],
}


def preprocessing():
    return ColumnTransformer([
        ("numeric", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), list(NUMERIC)),
        ("category", make_pipeline(
            SimpleImputer(strategy="constant", fill_value="(Missing)"),
            OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=120, max_categories=100,
                          dtype=np.float32),
        ), list(CATEGORICAL)),
    ], sparse_threshold=1.0)


def make_estimator(name, params, target):
    if name == "logistic":
        return LogisticRegression(max_iter=400, **params)
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=100, max_features="sqrt", n_jobs=WORKERS,
                                      random_state=SEED, **params)
    params = params.copy()
    weight = params["scale_pos_weight"]
    params["scale_pos_weight"] = 1.0 if weight == "unweighted" else np.sqrt((1 - target.mean()) / target.mean())
    return XGBClassifier(n_estimators=300, learning_rate=0.06, min_child_weight=10, subsample=0.85,
                         colsample_bytree=0.85, tree_method="hist", n_jobs=WORKERS,
                         random_state=SEED, **params)


def probability_logit(scores):
    return logit(np.clip(scores, 1e-7, 1 - 1e-7)).reshape(-1, 1)


@dataclass
class FittedModel:
    preprocessing: ColumnTransformer
    estimator: object
    calibrator: LogisticRegression | None
    parameters: dict

    def predict(self, frame, calibrated=True):
        raw = self.estimator.predict_proba(self.preprocessing.transform(features(frame)))[:, 1]
        if calibrated and self.calibrator is not None:
            return self.calibrator.predict_proba(probability_logit(raw))[:, 1]
        return raw


def develop(splits, families, label):
    train, tune, calibration, selection = (splits[name] for name in ("train", "tune", "calibration", "selection"))
    pre = preprocessing()
    x_train = pre.fit_transform(features(train))
    x_tune, x_cal, x_selection = [pre.transform(features(part)) for part in (tune, calibration, selection)]
    y_train, y_tune, y_cal, y_selection = [part[TARGET].to_numpy() for part in (train, tune, calibration, selection)]
    trials, calibration_trials, models = [], [], {}
    for name in families:
        best = None
        for params in GRIDS[name]:
            model = make_estimator(name, params, y_train)
            with threadpool_limits(limits=WORKERS):
                model.fit(x_train, y_train)
            tuning_scores = model.predict_proba(x_tune)[:, 1]
            ap = average_precision_score(y_tune, tuning_scores)
            print(f"{label} {name} {params}: tuning AP={ap:.6f}", flush=True)
            trials.append({"study": label, "model": name, "parameters": params, "tuning_ap": ap})
            if best is None or ap > best[0]:
                best = (ap, params, model)
        _, params, model = best
        raw_cal = model.predict_proba(x_cal)[:, 1]
        raw_select = model.predict_proba(x_selection)[:, 1]
        calibrator = LogisticRegression(C=1000).fit(probability_logit(raw_cal), y_cal)
        calibrated_select = calibrator.predict_proba(probability_logit(raw_select))[:, 1]
        raw_brier = brier_score_loss(y_selection, raw_select)
        mapped_brier = brier_score_loss(y_selection, calibrated_select)
        use_mapping = calibrator.coef_[0, 0] > 0 and mapped_brier < raw_brier
        calibration_trials.append({
            "study": label, "model": name, "raw_brier": raw_brier, "sigmoid_brier": mapped_brier,
            "sigmoid_slope": float(calibrator.coef_[0, 0]),
            "sigmoid_intercept": float(calibrator.intercept_[0]),
            "chosen": "sigmoid" if use_mapping else "identity",
            "selection_brier": mapped_brier if use_mapping else raw_brier,
        })
        models[name] = FittedModel(pre, model, calibrator if use_mapping else None, params)
    champion = min(calibration_trials, key=lambda row: row["selection_brier"])["model"]
    return models, champion, trials, calibration_trials
