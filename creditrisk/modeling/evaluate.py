"""Evaluate frozen models and publish aggregate reports plus local-only scores."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import joblib
import numpy as np
import pandas as pd

from creditrisk.paths import ARTIFACTS, DATABASE, MODELING_REPORTS
from creditrisk.profile import query, source_manifest

from .cohorts import FEATURES, TARGET, chronological_split, load_cohort
from .decisions import SCENARIOS, THRESHOLD_GRID, confusion, costs, risk_decile
from .explanations import explain
from .metrics import bootstrap_comparison, calibration_summary, performance, reliability, summarize_groups
from .plots import draw
from .train import STUDIES

OUTPUT = MODELING_REPORTS


def save_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def term_audit():
    with duckdb.connect(str(DATABASE), read_only=True) as db:
        return query(db, """
            SELECT CASE WHEN term_months IS NULL OR term_months <= 0 THEN 'missing_or_invalid'
                        WHEN term_months % 12 = 0 THEN 'multiple_of_12'
                        WHEN term_months % 6 = 0 THEN 'multiple_of_6_only' ELSE 'other' END AS term_pattern,
                   count(*) AS records, sum(charge_off_60m) AS events, avg(charge_off_60m) AS event_rate
            FROM loan_portfolio WHERE charge_off_60m IS NOT NULL
              AND first_disbursement_date < DATE '2016-10-01'
            GROUP BY 1 ORDER BY 1
        """)


def evaluate_study(cohort, study, settings):
    models = joblib.load(ARTIFACTS / f"{study}.joblib")
    splits = chronological_split(cohort, STUDIES[study])
    metrics, bins, matrices, cohorts = [], [], [], []
    predictions = {}
    for name, part in splits.items():
        if part.empty:
            continue
        metadata = {
            "study": study, "cohort": name, "records": len(part),
            "first_origination": str(part.first_disbursement_date.min().date()),
            "last_origination": str(part.first_disbursement_date.max().date()),
            "last_horizon_end": str(part.horizon_end.max().date()),
            "horizons_closed_by_test_start": int((part.horizon_end < pd.Timestamp(STUDIES[study].test_start)).sum()),
            "events": int(part[TARGET].sum()) if name != "score_only" else None,
        }
        cohorts.append(metadata)
        if name not in ("selection", "test"):
            continue
        target = part[TARGET].to_numpy()
        predictions[name] = {}
        prior = np.full(len(part), splits["train"][TARGET].mean())
        metrics.append({"study": study, "cohort": name, "model": "training_prevalence", "variant": "reference",
                        **performance(target, prior), "observed_rate": float(target.mean()),
                        "predicted_rate": float(prior.mean()), "records": len(target), "events": int(target.sum())})
        for model_name, model in models.items():
            raw, selected = model.predict(part, calibrated=False), model.predict(part)
            predictions[name][model_name] = selected
            for variant, probability in {"raw": raw, "selected": selected}.items():
                identifiers = {"study": study, "cohort": name, "model": model_name, "variant": variant}
                metrics.append({**identifiers, **performance(target, probability),
                                **calibration_summary(target, probability)})
                bins.extend({**identifiers, **row} for row in reliability(target, probability))
            thresholds = {"fixed_5pct": 0.05, **{
                f"{scenario}_{rule}": threshold
                for scenario, rules in settings["thresholds"][model_name].items()
                for rule, threshold in rules.items()
            }}
            matrices.extend({
                "study": study, "cohort": name, "model": model_name, "rule": rule,
                **confusion(target, selected, threshold),
            } for rule, threshold in thresholds.items())
    return models, splits, predictions, metrics, bins, matrices, cohorts


def business_outputs(splits, predictions, models, settings, output, local_output):
    champion = settings["champion"]
    cutpoints = settings["decile_cutpoints"]
    deciles, concentration, sensitivity, scores = [], [], [], []
    for name, part in splits.items():
        if part.empty:
            continue
        scores_by_model = predictions.get(name)
        if scores_by_model is None:
            scores_by_model = {model_name: model.predict(part) for model_name, model in models.items()}
        probability = scores_by_model[champion]
        risk = risk_decile(probability, cutpoints)
        scores.append(pd.DataFrame({"local_record_id": part.local_record_id, "origination_fy": part.origination_fy,
                                    "cohort": name, "risk_decile": risk, **scores_by_model}))
        if name not in ("selection", "test", "score_only"):
            continue
        analysis = part.assign(probability=probability, risk_decile=risk)
        observed = name != "score_only"
        deciles.append(summarize_groups(analysis, ["risk_decile"], include_observed=observed).assign(cohort=name))
        if name == "test":
            for field in ("project_state", "naics_sector", "amount_band", "term_band"):
                values = analysis[field].fillna("Unknown")
                values = values.where(values.map(values.value_counts()) >= 100, "Segments under 100")
                segment = summarize_groups(analysis.assign(segment=values), ["segment"])
                concentration.append(segment.assign(dimension=field))
        if observed:
            target = part[TARGET].to_numpy()
            for scenario in SCENARIOS:
                rules = settings["thresholds"][champion][scenario]
                thresholds = np.unique(np.r_[THRESHOLD_GRID, *rules.values()])
                for threshold in thresholds:
                    sensitivity.append({"cohort": name, "model": champion,
                                        "is_validation_threshold": threshold == rules["validation_threshold"],
                                        "is_bayes_threshold": threshold == rules["bayes_threshold"],
                                        **costs(target, probability, threshold, scenario)})
    all_scores = pd.concat(scores, ignore_index=True).sort_values("local_record_id")
    with duckdb.connect() as db:
        db.register("modeled_scores", all_scores)
        db.execute("COPY modeled_scores TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(local_output)])
    decile_report = pd.concat(deciles, ignore_index=True)
    decile_report.to_csv(output / "risk_deciles.csv", index=False)
    pd.concat(concentration, ignore_index=True).to_csv(output / "risk_concentration.csv", index=False)
    pd.DataFrame(sensitivity).to_csv(output / "cost_sensitivity.csv", index=False)
    return decile_report


def evaluate():
    fit = json.loads((ARTIFACTS / "fit_manifest.json").read_text(encoding="utf-8"))
    if fit["database"] != source_manifest(DATABASE) or fit["features"] != list(FEATURES):
        raise ValueError("Model artifacts and current dataset or feature contract differ. Run train first.")
    for name in STUDIES:
        path = ARTIFACTS / f"{name}.joblib"
        if fit.get("artifacts", {}).get(path.name) != source_manifest(path):
            raise ValueError(f"{path.name} does not match the fit manifest. Run train first.")
    cohort = load_cohort()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".eval-", dir=ARTIFACTS.parent) as directory:
        staging = Path(directory)
        output = staging / "reports"
        output.mkdir()
        all_metrics, all_reliability, all_matrices, all_cohorts = [], [], [], []
        summary = {"source_database": fit["database"], "models": {}, "explanation": {}}
        for study, settings in fit["studies"].items():
            models, splits, predictions, metrics, bins, matrices, cohorts = evaluate_study(cohort, study, settings)
            all_metrics.extend(metrics)
            all_reliability.extend(bins)
            all_matrices.extend(matrices)
            all_cohorts.extend(cohorts)
            champion = settings["champion"]
            summary["models"][study] = {"selected_on_validation": champion}
            if study == "retrospective":
                deciles = business_outputs(splits, predictions, models, settings, output, staging / "loan_scores.parquet")
                target = splits["test"][TARGET].to_numpy()
                importance, examples, summary["explanation"] = explain(models["xgboost"], splits["test"])
                importance.to_csv(output / "tree_shap_importance.csv", index=False)
                examples.to_csv(staging / "tree_shap_examples.csv", index=False)
                logistic = models["logistic"]
                pd.DataFrame({
                    "encoded_feature": logistic.preprocessing.get_feature_names_out(),
                    "log_odds_coefficient": logistic.estimator.coef_[0],
                }).to_csv(output / "logistic_coefficients.csv", index=False)
                boot = bootstrap_comparison(target, predictions["test"][champion], predictions["test"]["logistic"],
                                            splits["test"]["first_disbursement_date"])
                save_json(output / "test_uncertainty.json", boot)
                report_matrices = {row["rule"]: row for row in matrices
                                   if row["cohort"] == "test" and row["model"] == champion}
                draw(output, target, predictions["test"], pd.DataFrame(bins), deciles, importance, champion, report_matrices)
                year_report = splits["test"].assign(probability=predictions["test"][champion])
                summarize_groups(year_report, ["origination_fy"]).to_csv(output / "test_by_fiscal_year.csv", index=False)
        for name, rows in {"metrics": all_metrics, "reliability": all_reliability,
                           "confusion_matrices": all_matrices, "cohort_audit": all_cohorts,
                           "term_leakage_audit": term_audit()}.items():
            pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
        save_json(output / "development_decisions.json", fit)
        summary["scores"] = source_manifest(staging / "loan_scores.parquet")
        save_json(output / "run_summary.json", summary)
        for name in ("loan_scores.parquet", "tree_shap_examples.csv"):
            os.replace(staging / name, ARTIFACTS / name)
        for item in sorted(output.iterdir(), key=lambda path: path.name == "run_summary.json"):
            os.replace(item, OUTPUT / item.name)
    print(f"Saved aggregate model validation to {OUTPUT}", flush=True)


if __name__ == "__main__":
    evaluate()
