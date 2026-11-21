"""Fit full-cohort benchmark models and freeze selection before test evaluation."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import sklearn
import xgboost

from creditrisk.paths import ARTIFACTS, DATABASE
from creditrisk.profile import source_manifest

from .cohorts import FEATURES, MATURE, PRIMARY, TARGET, chronological_split, load_cohort
from .decisions import fit_deciles, freeze_thresholds
from .estimators import GRIDS, SEED, develop

STUDIES = {"retrospective": PRIMARY, "horizon_mature": MATURE}


def train():
    cohort = load_cohort()
    manifest = {
        "seed": SEED, "target": TARGET, "features": FEATURES,
        "database": source_manifest(DATABASE),
        "sklearn": sklearn.__version__, "xgboost": xgboost.__version__, "studies": {},
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".fit-", dir=ARTIFACTS.parent) as temporary:
        staging = Path(temporary)
        for study, windows in STUDIES.items():
            splits = chronological_split(cohort, windows)
            families = tuple(GRIDS) if study == "retrospective" else ("logistic", "xgboost")
            models, champion, tuning, mappings = develop(splits, families, study)
            selection = splits["selection"]
            predictions = {name: model.predict(selection) for name, model in models.items()}
            thresholds = {name: freeze_thresholds(selection[TARGET].to_numpy(), scores)
                          for name, scores in predictions.items()}
            manifest["studies"][study] = {
                "windows": vars(windows), "champion": champion, "tuning": tuning, "calibration": mappings,
                "thresholds": thresholds, "decile_cutpoints": fit_deciles(predictions[champion]),
            }
            joblib.dump(models, staging / f"{study}.joblib", compress=3)
            if "xgboost" in models:
                models["xgboost"].estimator.save_model(staging / f"{study}_xgboost.ubj")
            print(f"{study} locked champion: {champion}", flush=True)
        manifest["artifacts"] = {file.name: source_manifest(file) for file in sorted(staging.iterdir())}
        (staging / "fit_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for file in sorted(staging.iterdir(), key=lambda path: path.name == "fit_manifest.json"):
            os.replace(file, ARTIFACTS / file.name)


if __name__ == "__main__":
    train()
