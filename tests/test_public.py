"""Exercise the Cloud bundle and public controls without private artifacts."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from creditrisk.dashboard import public_data
from creditrisk.dashboard.catalog import MODELS, SECTORS
from creditrisk.dashboard.ui import export
from creditrisk.paths import ROOT


class PublicRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata, cls.tables = public_data.load(public_data.release_key())

    def test_package_file_and_field_whitelists(self):
        self.assertEqual({file.name for file in public_data.DIRECTORY.iterdir()},
                         set(public_data.SCHEMAS) | {"manifest.json"})
        approved = {
            "state": r"(?:[A-Z]{2}|Unknown|Other segments \(pooled\))",
            "vintage": r"20(?:1[0-9]|2[01])",
            "decile": r"(?:[1-9]|10|Other segments \(pooled\))",
            "size": r"(?:Under \$50k|\$50k to <\$150k|\$150k to <\$500k|\$500k to <\$1m|\$1m and above)",
            "term": r"(?:1–60|61–120|121–240|241\+|Other segments \(pooled\))",
            "collateral": r"(?:Yes|No|Unknown)",
            "portfolio": r"All eligible",
        }
        for name in ("overview.csv", "explorer.csv"):
            for dimension, rows in self.tables[name].groupby("dimension"):
                if dimension == "industry":
                    self.assertLessEqual(set(rows.segment), {*SECTORS, public_data.OTHER, "Unknown"})
                else:
                    self.assertTrue(rows.segment.str.fullmatch(approved[dimension]).all(), dimension)
            self.assertFalse(self.tables[name].duplicated(subset=["dimension", "segment"]).any())

    def test_partitions_and_complements_have_disclosure_support(self):
        overview, explorer = self.tables["overview.csv"], self.tables["explorer.csv"]
        for data, total, events, principal in ((overview, 477797, 19388, 180041494043),
                                                (explorer, 103136, 4631, 43826361500)):
            self.assertTrue(data.records.ge(public_data.MIN_RECORDS).all())
            self.assertTrue(data.events.ge(public_data.MIN_OUTCOME).all())
            self.assertTrue((data.records - data.events).ge(public_data.MIN_OUTCOME).all())
            for _, group in data.groupby("dimension"):
                self.assertEqual((group.records.sum(), group.events.sum(), group.approved_usd.sum()),
                                 (total, events, principal))
                if len(group) > 1:
                    self.assertTrue((total - group.records).ge(public_data.MIN_RECORDS).all())
                    self.assertTrue((events - group.events).ge(public_data.MIN_OUTCOME).all())
        common = overview.merge(explorer, on=["dimension", "segment"], suffixes=("_all", "_test"))
        common = common.loc[common.segment.ne(public_data.OTHER)]
        self.assertTrue((common.records_all - common.records_test).ge(public_data.MIN_RECORDS).all())
        self.assertTrue((common.events_all - common.events_test).ge(public_data.MIN_OUTCOME).all())
        archive = pd.read_csv(ROOT / "reports" / "portfolio_summary.csv", dtype={"segment": str})
        archive["dimension"] = archive.dimension.replace(
            {"naics_sector": "industry", "project_state": "state", "amount_band": "size"})
        differences = overview.query("dimension in ['industry','state','size','collateral']").merge(
            archive[["dimension", "segment", "records"]], on=["dimension", "segment"], suffixes=("_eligible", "_archive"))
        rest = differences.records_archive - differences.records_eligible
        self.assertTrue((rest.eq(0) | rest.ge(public_data.MIN_RECORDS)).all())

    def test_original_metrics_and_common_curve_bands(self):
        metrics = self.tables["metrics.csv"]
        xgb = metrics.query("study == 'retrospective' and cohort == 'test' and model == 'xgboost' and variant == 'selected'").iloc[0]
        self.assertEqual((round(xgb.roc_auc, 4), round(xgb.pr_auc_average_precision, 5), round(xgb.brier, 5)),
                         (0.7165, 0.09508, 0.04185))
        for model in MODELS:
            bins = self.tables["calibration.csv"].query("model == @model").sort_values("predicted_rate", ascending=False)
            self.assertEqual((bins.records.sum(), bins.events.sum()), (103136, 4631))
            self.assertTrue(bins.records.ge(public_data.MIN_RECORDS).all())
            self.assertTrue(bins.events.ge(public_data.MIN_OUTCOME).all())
            curves = self.tables["curves.csv"].query("model == @model and step > 0")
            self.assertEqual(len(bins), len(curves))
            self.assertAlmostEqual(curves.recall.iloc[-1], 1)
            for expected, actual in zip(bins.events.cumsum() / 4631, curves.recall):
                self.assertAlmostEqual(expected, actual, places=10)

    def test_scenarios_and_restricted_download(self):
        scenarios = self.tables["stress.csv"]
        self.assertEqual(scenarios.multiplier.tolist(), [1.0, 1.25, 1.75])
        self.assertEqual(scenarios.proxy_basis_usd.tolist(), [10000000] * 3)
        self.assertEqual((scenarios.weighted_event_indicator * 100).round(2).tolist(), [2.32, 2.90, 4.06])
        public = self.tables["explorer.csv"].query("dimension == 'state' and segment == 'CA'")
        with patch("creditrisk.dashboard.ui.st.download_button") as button:
            export(public, "approved.csv")
        result = pd.read_csv(BytesIO(button.call_args.args[1]))
        self.assertEqual(tuple(result.columns), public_data.SCHEMAS["explorer.csv"])
        self.assertEqual(result.segment.tolist(), ["CA"])
        self.assertEqual(result.records.tolist(), [12475])


class PublicPages(unittest.TestCase):
    def test_entrypoint_uses_the_aggregate_release(self):
        with patch.dict("os.environ", {"CREDITRISK_MODE": "public"}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=35).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.metric[0].value, "477,797")
        self.assertTrue(any("Public demo" in item.value for item in app.info))

    def test_all_pages_and_supported_filters(self):
        setup = (
            "from creditrisk.dashboard import public_data, public_pages\n"
            "manifest, tables = public_data.load(public_data.release_key())\n"
        )
        with TemporaryDirectory(dir=ROOT) as scratch:
            script = Path(scratch) / "page.py"
            for call in ("executive(tables)", "model_lab(manifest, tables)", "risk_explorer(tables)",
                         "stress_testing(tables)", "model_governance(manifest, tables)"):
                with self.subTest(page=call):
                    script.write_text(setup + f"public_pages.{call}\n", encoding="utf-8")
                    app = AppTest.from_file(str(script), default_timeout=35).run()
                    self.assertFalse(app.exception, [error.message for error in app.exception])
                    self.assertTrue(app.get("download_button"))
                    if call.startswith("risk_explorer"):
                        app.selectbox[0].select("state").run()
                        app.selectbox[1].select("CA").run()
                        self.assertFalse(app.exception)
                        self.assertEqual(app.dataframe[0].value.records.tolist(), [12475])
                        self.assertEqual(len(app.selectbox), 2)
