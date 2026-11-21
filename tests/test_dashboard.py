"""Exercise dashboard data queries and the Streamlit page controls."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb
import pandas as pd
from streamlit.testing.v1 import AppTest

from creditrisk.dashboard import data
from creditrisk.dashboard.lab import comparison
from creditrisk.dashboard.ui import export
from creditrisk.paths import ROOT
from creditrisk.profile import source_manifest


class DashboardData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = data.release_key()
        cls.release = data.release(cls.key)
        cls.model = cls.release["champion"]

    def test_overview_reconciles_to_eligible_release_by_each_dimension(self):
        rows = data.aggregates(self.key, data.Scope("all"), ("portfolio", "industry", "state", "vintage"), self.model)
        totals = rows.groupby("dimension")[["records", "events", "approved_usd"]].sum()
        with duckdb.connect(str(data.DATABASE), read_only=True) as db:
            records, events, dollars = db.execute("""
                SELECT count(*), sum(charge_off_60m), sum(gross_approval)
                FROM loan_portfolio WHERE charge_off_60m IS NOT NULL
            """).fetchone()
        for row in totals.itertuples():
            self.assertEqual((row.records, row.events), (records, events))
            self.assertAlmostEqual(row.approved_usd, float(dollars), places=2)

    def test_combined_filters_and_empty_selection(self):
        state = data.Scope("test", (("state", ("CA",)),))
        combined = data.Scope("test", (("state", ("CA",)), ("vintage", ("2019",))))
        results = [data.aggregates(self.key, scope, ("portfolio", "state", "vintage"), self.model)
                   for scope in (state, combined)]
        self.assertLess(results[1].loc[results[1].dimension.eq("portfolio"), "records"].item(),
                        results[0].loc[results[0].dimension.eq("portfolio"), "records"].item())
        self.assertEqual(results[1].loc[results[1].dimension.eq("vintage"), "segment"].tolist(), ["2019"])
        no_match = data.Scope("test", (("vintage", ("2021",)),))
        self.assertTrue(data.aggregates(self.key, no_match, ("portfolio",), self.model).empty)

    def test_stress_caps_loan_probability_before_amount_weighting(self):
        scope = data.Scope("test")
        rows = data.aggregates(self.key, scope, ("portfolio", "industry"), self.model, stress=(1.25, 20.0))
        row = rows.loc[rows.dimension.eq("portfolio")].iloc[0]
        with duckdb.connect(str(data.DATABASE), read_only=True) as db:
            amounts = db.execute("""
                SELECT p.gross_approval::DOUBLE AS approved, s.xgboost::DOUBLE AS probability
                FROM loan_portfolio p JOIN read_parquet(?) s ON p.rowid = s.local_record_id
                WHERE s.cohort = 'test'
            """, [str(data.SCORES)]).fetchdf()
        for name, factor in (("baseline", 1.0), ("moderate", 1.25), ("severe", 20.0)):
            expected = (amounts.approved * amounts.probability.mul(factor).clip(upper=1)).sum() / amounts.approved.sum()
            self.assertAlmostEqual(row[name], expected, places=10)
        self.assertLess(row.severe, min(row.baseline * 20.0, 1))
        with self.assertRaises(ValueError):
            data.aggregates(self.key, scope, ("portfolio",), self.model, stress=(2, 1))

    def test_threshold_diagnostics_match_saved_holdout(self):
        expected = pd.read_csv(data.REPORTS / "confusion_matrices.csv").query(
            "study == 'retrospective' and cohort == 'test' and model == 'xgboost' and rule == 'fixed_5pct'"
        ).iloc[0]
        actual = data.model_diagnostics(self.key, "test", "xgboost", 0.05)
        self.assertEqual(tuple(actual[key] for key in ("tn", "fp", "fn", "tp")),
                         tuple(expected[key] for key in ("tn", "fp", "fn", "tp")))

    def test_csv_export_round_trips_filtered_aggregates(self):
        scope = data.Scope("test", (("state", ("CA",)),))
        filtered = data.aggregates(self.key, scope, ("state",), self.model)
        with patch("creditrisk.dashboard.ui.st.download_button") as button:
            export(filtered, "filtered_segments.csv")
        self.assertEqual(button.call_args.kwargs["file_name"], "filtered_segments.csv")
        self.assertEqual(button.call_args.kwargs["mime"], "text/csv")
        downloaded = pd.read_csv(BytesIO(button.call_args.args[1]))
        self.assertEqual(downloaded.segment.tolist(), ["CA"])
        self.assertEqual(downloaded.records.tolist(), [12475])
        self.assertEqual(list(downloaded.columns), list(filtered.columns))

    def test_release_rejects_a_score_file_with_the_wrong_fingerprint(self):
        def mismatched_score(path):
            fingerprint = source_manifest(path)
            if path == data.SCORES:
                fingerprint["sha256"] = "0" * 64
            return fingerprint

        with patch("creditrisk.dashboard.data.source_manifest", side_effect=mismatched_score):
            with self.assertRaisesRegex(ValueError, "different builds"):
                data.release(self.key + (("fingerprint-regression", 0, 0),))


class DashboardPages(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix=".dashboard-test-", dir=data.SCORES.parent.parent)
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def page(self, name):
        script = self.directory / f"{name}.py"
        script.write_text(
            f"from creditrisk.dashboard import {name}\n"
            "from creditrisk.dashboard.data import release, release_key\n"
            f"key = release_key()\n{name}.render(key, release(key))\n",
            encoding="utf-8",
        )
        app = AppTest.from_file(str(script), default_timeout=35).run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def test_main_router_and_default_overview(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=35).run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertFalse(app.error, [error.value for error in app.error])
        self.assertEqual(app.metric[0].value, "477,797")
        self.assertEqual(len(app.get("plotly_chart")), 5)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_lab_threshold_changes_matrix_and_model_switch_updates_metrics(self):
        app = self.page("lab")
        key = data.release_key()
        expected = comparison(key, "test").set_index("model")
        selected = data.release(key)["champion"]
        self.assertEqual(app.metric[0].value, f"{expected.loc[selected, 'roc_auc']:.4f}")
        app.slider[0].set_value(5.0).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(header.value == "Confusion matrix at 5.0%" for header in app.subheader))
        app.selectbox[0].select("logistic").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, f"{expected.loc['logistic', 'roc_auc']:.4f}")
        self.assertGreaterEqual(len(app.get("download_button")), 2)

    def test_explorer_applies_filters_and_handles_empty_results(self):
        app = self.page("explorer")
        self.assertEqual(app.metric[0].value, "103,136")
        app.multiselect(key="explorer_state").set_value(["CA"])
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "12,475")
        app.multiselect(key="explorer_vintage").set_value(["2021"])
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("No records match" in message.value for message in app.info))

    def test_stress_controls_and_governance_study(self):
        app = self.page("stress")
        self.assertEqual(app.metric[0].value, "$10.00M")
        initial = app.metric[3].value
        app.number_input[1].set_value(2.0).run()
        self.assertFalse(app.exception)
        self.assertGreater(float(app.metric[3].value.strip("%")), float(initial.strip("%")))
        app.number_input[0].set_value(3.0).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Set the severe multiplier" in message.value for message in app.warning))
        gov = self.page("governance")
        gov.radio[0].set_value("horizon_mature").run()
        self.assertFalse(gov.exception)
        self.assertTrue(any("All development horizons closed" in item.value for item in gov.caption))


if __name__ == "__main__":
    unittest.main()
