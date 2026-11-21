"""Exercise the production SQL and reconcile the saved release to the source."""

from collections import Counter
import csv
from datetime import date
from hashlib import sha256
import json
import unittest

import duckdb

from creditrisk.pipeline import DATABASE, REPORTS, SNAPSHOT, SOURCE_CSV, SOURCE_DICTIONARY, read_contract, run_sql
from creditrisk.profile import source_manifest
from creditrisk.schema import FIELD_GROUPS, TYPED_COLUMNS


class TargetRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = duckdb.connect()
        fields = ", ".join(f'"{name}" VARCHAR' for name in read_contract(SOURCE_CSV, SOURCE_DICTIONARY))
        cls.db.execute(f"CREATE TABLE raw_unique ({fields}, source_copies BIGINT)")
        fixtures = [
            ("same_day", "2020-02-29", "CHGOFF", "2020-02-29", None, "100"),
            ("leap_anniversary", "2020-02-29", "CHGOFF", "2025-02-28", None, "100"),
            ("day_after", "2020-02-29", "CHGOFF", "2025-03-01", None, "100"),
            ("full_payoff", "2020-02-29", "P I F", None, "2020-03-01", "0"),
            ("exempt", "2021-09-30", "EXEMPT", None, None, "0"),
            ("immature", "2021-10-01", "CHGOFF", "2022-01-01", None, "100"),
            ("missing_funding", None, "EXEMPT", None, None, "0"),
            ("unfunded", None, "COMMIT", None, None, "0"),
            ("cancelled", "2020-02-29", "CANCLD", None, None, "0"),
            ("invalid_funding", "bad-date", "EXEMPT", None, None, "0"),
            ("approval_after_funding", "2019-12-31", "EXEMPT", None, None, "0"),
            ("missing_event", "2020-02-29", "CHGOFF", None, None, "100"),
            ("bad_event", "2020-02-29", "CHGOFF", "bad-date", None, "100"),
            ("future_event", "2020-02-29", "CHGOFF", "2026-10-01", None, "100"),
            ("early_event", "2020-02-29", "CHGOFF", "2020-02-28", None, "100"),
            ("missing_payoff", "2020-02-29", "PIF", None, None, "0"),
            ("conflict", "2020-02-29", "EXEMPT", None, None, "50"),
            ("unknown_status", "2020-02-29", "OTHER", None, None, "0"),
        ]
        cls.db.executemany("""
            INSERT INTO raw_unique (ProcessingMethod, FirstDisbursementDate, LoanStatus,
                ChargeOffDate, PaidInFullDate, GrossChargeOffAmount, AsOfDate, ApprovalDate, source_copies)
            VALUES (?, ?, ?, ?, ?, ?, '2026-09-30', '2020-01-01', 1)
        """, fixtures)
        run_sql(cls.db, "01_clean.sql")
        run_sql(cls.db, "02_target.sql")
        cls.labels = {
            name: (reason, label) for name, reason, label in cls.db.execute("""
                SELECT processing_method, target_eligibility, charge_off_60m FROM loan_portfolio
            """).fetchall()
        }

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_inclusive_horizon_uses_calendar_months(self):
        for name, label in [("same_day", 1), ("leap_anniversary", 1), ("day_after", 0), ("exempt", 0)]:
            with self.subTest(name=name):
                self.assertEqual(self.labels[name], ("eligible", label))
        self.assertEqual(self.db.execute("""
            SELECT horizon_end FROM loan_portfolio WHERE processing_method = 'leap_anniversary'
        """).fetchone()[0], date(2025, 2, 28))

    def test_terminal_payoff_and_full_seasoning(self):
        self.assertEqual(self.labels["full_payoff"], ("eligible", 0))
        self.assertEqual(self.labels["immature"], ("incomplete_60m_followup", None))

    def test_origination_exclusions(self):
        for name, reason in {
            "missing_funding": "missing_first_disbursement",
            "unfunded": "cancelled_or_undisbursed",
            "cancelled": "cancelled_or_undisbursed",
            "invalid_funding": "invalid_first_disbursement",
            "approval_after_funding": "inconsistent_origination_date",
        }.items():
            with self.subTest(name=name):
                self.assertEqual(self.labels[name], (reason, None))

    def test_uncertain_outcomes_excluded(self):
        for name, reason in {
            "missing_event": "chargeoff_date_missing",
            "bad_event": "invalid_outcome_date",
            "future_event": "outcome_date_outside_observation",
            "early_event": "outcome_date_outside_observation",
            "missing_payoff": "payoff_date_missing",
            "conflict": "status_outcome_conflict",
            "unknown_status": "unknown_status",
        }.items():
            with self.subTest(name=name):
                self.assertEqual(self.labels[name], (reason, None))


class BuiltRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = duckdb.connect(str(DATABASE), read_only=True)
        cls.report = json.loads((REPORTS / "data_quality.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_source_release_and_exact_duplicate_counts(self):
        self.assertEqual(self.report["sources"]["csv"], source_manifest(SOURCE_CSV))
        self.assertEqual(self.report["sources"]["dictionary"], source_manifest(SOURCE_DICTIONARY))
        # Independent streaming CSV parser. Hold only transient digests and counts.
        frequencies = Counter()
        raw_status = Counter()
        missing = Counter()
        with SOURCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
            records = csv.reader(handle, strict=True)
            header = next(records)
            status_index = header.index("LoanStatus")
            for row in records:
                self.assertEqual(len(row), len(header))
                frequencies[sha256(json.dumps(row, ensure_ascii=False).encode()).digest()] += 1
                raw_status[row[status_index]] += 1
                missing.update(name for name, value in zip(header, row) if not value.strip())
        self.assertEqual(self.report["duplicate_check"], {
            "source_rows": frequencies.total(),
            "distinct_source_rows": len(frequencies),
            "duplicate_groups": sum(count > 1 for count in frequencies.values()),
            "excess_exact_duplicate_rows": frequencies.total() - len(frequencies),
        })
        self.assertEqual(raw_status, {
            row["raw_value"]: row["records"] for row in self.report["source_categories"]["LoanStatus"]
        })
        with (REPORTS / "field_profile.csv").open(encoding="utf-8", newline="") as handle:
            self.assertEqual(
                {row["source_field"]: int(row["source_blank_rows"]) for row in csv.DictReader(handle)},
                {name: missing[name] for name in header},
            )

    def test_portfolio_and_labels_reconcile(self):
        expected = self.report["portfolio_totals"]
        actual = self.db.execute("""
            SELECT count(*), count(charge_off_60m), sum(charge_off_60m), min(snapshot_date),
                   max(snapshot_date), count(DISTINCT program) FROM loan_portfolio
        """).fetchone()
        self.assertEqual(actual, (544615, 477797, 19388, SNAPSHOT, SNAPSHOT, 1))
        self.assertEqual(actual[:3], (expected["records"], expected["eligible_60m_records"], expected["chargeoffs_60m"]))
        self.assertEqual(self.db.execute("""
            SELECT count(*) FROM loan_portfolio WHERE
                (target_eligibility = 'eligible') <> (charge_off_60m IS NOT NULL)
                OR (charge_off_60m IS NOT NULL AND (
                    first_disbursement_date IS NULL OR horizon_end > snapshot_date
                    OR loan_status NOT IN ('PIF', 'CHGOFF', 'EXEMPT')
                    OR charge_off_60m <> CASE
                        WHEN charge_off_date BETWEEN first_disbursement_date AND horizon_end THEN 1 ELSE 0 END
                ))
        """).fetchone()[0], 0)

    def test_feature_allowlist_and_private_columns(self):
        columns = lambda table: {row[0].lower() for row in self.db.execute(f"DESCRIBE {table}").fetchall()}
        candidates = FIELD_GROUPS["Approval/disbursement candidate"]
        self.assertEqual(columns("modeling_cohort"), {TYPED_COLUMNS[name] for name in candidates} | {"charge_off_60m"})
        self.assertEqual(columns("loan_portfolio") & {"borrname", "borrstreet", "borrzip", "locationid", "bankname"}, set())
        self.assertEqual({row[0] for row in self.db.execute("SHOW TABLES").fetchall()},
                         {"loan_portfolio", "modeling_cohort", "portfolio_summary"})

    def test_aggregations_reconcile_and_empty_denominators_are_null(self):
        groups = self.db.execute("""
            SELECT dimension, sum(records), sum(eligible_60m_records), sum(chargeoffs_60m)
            FROM portfolio_summary GROUP BY 1
        """).fetchall()
        self.assertEqual({row[0] for row in groups}, {
            "portfolio", "origination_year", "approval_fy", "project_state", "naics_sector",
            "naics_code", "amount_band", "term_band", "collateral", "loan_status",
        })
        self.assertTrue(all(row[1:] == (544615, 477797, 19388) for row in groups))
        self.assertEqual(self.db.execute("""
            SELECT count(*) FROM portfolio_summary WHERE
                (eligible_60m_records = 0) <> (chargeoff_60m_pct IS NULL)
                OR chargeoffs_60m IS NULL OR chargeoffs_60m > eligible_60m_records
        """).fetchone()[0], 0)

    def test_public_portfolio_export_omits_sparse_segments(self):
        with (REPORTS / "portfolio_summary.csv").open(encoding="utf-8", newline="") as handle:
            public_rows = list(csv.DictReader(handle))
        self.assertTrue(all(int(row["records"]) >= 10 for row in public_rows))
        self.assertEqual(len(public_rows), self.db.execute(
            "SELECT count(*) FROM portfolio_summary WHERE records >= 10"
        ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
