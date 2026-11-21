"""Validate chronological isolation, estimators, and produced model outputs."""

import json
import unittest

import duckdb
import joblib
import numpy as np
import pandas as pd

from creditrisk.modeling.cohorts import FEATURES, MATURE, PRIMARY, TARGET, chronological_split, features, load_cohort
from creditrisk.modeling.decisions import confusion, costs, fit_deciles, risk_decile
from creditrisk.modeling.estimators import preprocessing
from creditrisk.modeling.metrics import performance, reliability
from creditrisk.modeling.train import ARTIFACTS
from creditrisk.paths import MODELING_REPORTS
from creditrisk.profile import source_manifest


class MetricTests(unittest.TestCase):
    def test_metrics_match_hand_calculation_and_reject_invalid_scores(self):
        target = np.array([0, 0, 1, 1])
        scores = np.array([0.1, 0.4, 0.35, 0.8])
        result = performance(target, scores)
        self.assertAlmostEqual(result["roc_auc"], 0.75)
        self.assertAlmostEqual(result["pr_auc_average_precision"], (1 + 2 / 3) / 2)
        self.assertAlmostEqual(result["brier"], (0.1**2 + 0.4**2 + 0.65**2 + 0.2**2) / 4)
        with self.assertRaises(ValueError):
            performance(target, np.array([0, 1.01, 0.5, 0.5]))

    def test_inclusive_threshold_and_hypothetical_cost(self):
        target = np.array([0, 0, 1, 1])
        scores = np.array([0.1, 0.4, 0.35, 0.8])
        row = confusion(target, scores, 0.4)
        self.assertEqual((row["tn"], row["fp"], row["fn"], row["tp"]), (1, 1, 1, 1))
        self.assertEqual((row["precision"], row["recall"]), (0.5, 0.5))
        self.assertEqual(costs(target, scores, 0.4, "base")["total_cost_usd"], 5500)
        self.assertIsNone(confusion(target, scores, 1)["precision"])

    def test_reliability_and_decile_boundaries(self):
        rows = reliability(np.array([0, 1, 1]), np.array([0, 0.051, 1]))
        self.assertEqual([row["bin_low"] for row in rows], [0, 0.05, 0.95])
        self.assertEqual(sum(row["records"] for row in rows), 3)
        cutpoints = fit_deciles(np.arange(101) / 100)
        np.testing.assert_array_equal(risk_decile(np.array([0, 0.1, 1]), cutpoints), [1, 2, 10])


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_cohort()

    def test_fiscal_boundaries_and_no_overlap(self):
        splits = chronological_split(self.data, PRIMARY)
        self.assertEqual({name: len(frame) for name, frame in splits.items()},
                         {"train": 254340, "tune": 56652, "calibration": 27252, "selection": 29940,
                          "test": 103136, "score_only": 6477})
        self.assertEqual(sum(len(part) for part in splits.values()), len(self.data))
        self.assertTrue(pd.concat([part.local_record_id for part in splits.values()]).is_unique)
        self.assertEqual(set(splits["test"].origination_fy), {2018, 2019})
        self.assertEqual(splits["train"].origination_fy.min(), 2010)
        self.assertEqual(splits["train"].origination_fy.max(), 2015)
        self.assertEqual(int(self.data[TARGET].sum()), 19388)

    def test_maturity_sensitivity_contains_no_unclosed_development_horizons(self):
        strict = chronological_split(self.data, MATURE)
        common = chronological_split(self.data, PRIMARY)
        np.testing.assert_array_equal(strict["test"].local_record_id, common["test"].local_record_id)
        development = pd.concat([strict[key] for key in ("train", "tune", "calibration", "selection")])
        self.assertTrue((development.horizon_end < pd.Timestamp(MATURE.test_start)).all())

    def test_allowlist_excludes_metadata_and_suspect_term(self):
        self.assertEqual(tuple(features(self.data.head()).columns), FEATURES)
        forbidden = {"loan_status", "paid_in_full_date", "charge_off_date", "gross_charge_off_amount",
                     "sold_sec_mrkt_ind", "term_months", "term_band", "first_disbursement_date",
                     "origination_fy", "approval_fy", "horizon_end", "local_record_id", TARGET}
        self.assertFalse(forbidden.intersection(FEATURES))

    def test_fitted_preprocessing_uses_training_values_and_handles_unseen_category(self):
        split = chronological_split(self.data)
        train = features(split["train"])
        pre = preprocessing().fit(train)
        imputer = pre.named_transformers_["numeric"].named_steps["simpleimputer"]
        self.assertAlmostEqual(imputer.statistics_[0], train["gross_approval"].median())
        self.assertEqual(tuple(pre.feature_names_in_), FEATURES)
        held = features(split["test"].head(2))
        held["processing_method"] = "held-out-only program"
        transformed = pre.transform(held)
        self.assertTrue(np.isfinite(transformed.data).all())
        self.assertFalse(any("held-out-only" in name for name in pre.get_feature_names_out()))

    def test_local_scores_cover_all_eligible_rows_and_match_saved_models(self):
        manifest = json.loads((ARTIFACTS / "fit_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(manifest["features"]), FEATURES)
        for name, fingerprint in manifest["artifacts"].items():
            self.assertEqual(source_manifest(ARTIFACTS / name), fingerprint)
        summary = json.loads((MODELING_REPORTS / "run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["scores"], source_manifest(ARTIFACTS / "loan_scores.parquet"))
        models = joblib.load(ARTIFACTS / "retrospective.joblib")
        self.assertEqual(set(models), {"logistic", "random_forest", "xgboost"})
        with duckdb.connect() as db:
            db.execute("CREATE TABLE scores AS SELECT * FROM read_parquet(?)", [str(ARTIFACTS / "loan_scores.parquet")])
            records, unique, invalid = db.execute("""
                SELECT count(*), count(DISTINCT local_record_id),
                    count(*) FILTER (WHERE risk_decile IS NULL OR risk_decile NOT BETWEEN 1 AND 10
                        OR logistic IS NULL OR NOT isfinite(logistic) OR logistic NOT BETWEEN 0 AND 1
                        OR random_forest IS NULL OR NOT isfinite(random_forest) OR random_forest NOT BETWEEN 0 AND 1
                        OR xgboost IS NULL OR NOT isfinite(xgboost) OR xgboost NOT BETWEEN 0 AND 1)
                FROM scores
            """).fetchone()
            self.assertEqual((records, unique, invalid), (len(self.data), len(self.data), 0))
            sample = db.execute("SELECT * FROM scores WHERE cohort = 'test' ORDER BY local_record_id LIMIT 100").fetchdf()
        joined = sample.merge(self.data, on="local_record_id", validate="one_to_one")
        for name, model in models.items():
            np.testing.assert_allclose(model.predict(joined), joined[name], rtol=1e-6, atol=1e-8)


if __name__ == "__main__":
    unittest.main()
