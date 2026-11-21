"""Build the local DuckDB portfolio and aggregate reports from raw SBA files."""

import argparse
import csv
from datetime import date
from pathlib import Path
import os
from tempfile import TemporaryDirectory

import duckdb
from openpyxl import load_workbook

from . import charts
from .paths import DATABASE, REPORTS, ROOT, SOURCE_CSV, SOURCE_DICTIONARY
from .profile import field_profile, source_manifest, write_reports
from .schema import FIELD_ROLES

SNAPSHOT = date(2026, 9, 30)


def run_sql(db, name):
    db.execute((ROOT / "sql" / name).read_text(encoding="utf-8"))


def read_contract(source, dictionary):
    with source.open(encoding="utf-8-sig", newline="") as handle:
        names = next(csv.reader(handle))
    workbook = load_workbook(dictionary, read_only=True, data_only=True)
    try:
        definitions = {
            row[0]: row[1] for row in workbook["7(a) Data Dictionary"].iter_rows(
                min_row=2, max_col=2, values_only=True
            ) if row[0] and row[1]
        }
    finally:
        workbook.close()
    if len(names) != len(set(names)) or set(names) != set(definitions) or set(names) != set(FIELD_ROLES):
        raise ValueError("CSV header, 7(a) dictionary and field inventory must match.")
    return names


def load_source(db, source):
    inferred = db.execute(
        "SELECT Columns FROM sniff_csv(?, sample_size = 50000)", [str(source)]
    ).fetchone()[0]
    db.execute("""
        CREATE TEMP TABLE raw_unique AS
        SELECT *, count(*) AS source_copies
        FROM read_csv(?, header = true, all_varchar = true, delim = ',', quote = '"',
                      escape = '"', strict_mode = true, ignore_errors = false)
        GROUP BY ALL
    """, [str(source)])
    return {column["name"]: column["type"] for column in inferred}


def validate_release(db):
    total, wrong_snapshot, wrong_program, wrong_fy = db.execute("""
        SELECT count(*), count_if(snapshot_date IS DISTINCT FROM ?),
            count_if(program IS DISTINCT FROM '7A'),
            count_if(approval_fy IS NULL OR approval_fy NOT BETWEEN 2010 AND 2019)
        FROM typed
    """, [SNAPSHOT]).fetchone()
    if not total or wrong_snapshot or wrong_program or wrong_fy:
        raise ValueError(
            f"Unexpected release: {total} records, {wrong_snapshot} wrong snapshots, "
            f"{wrong_program} wrong programs, {wrong_fy} fiscal years outside FY2010–FY2019."
        )


def validate_output(db):
    invalid, cohort, eligible, agreement = db.execute("""
        SELECT
            (SELECT count(*) FROM loan_portfolio WHERE
                (charge_off_60m IS NOT NULL) <> (target_eligibility = 'eligible')
                OR charge_off_60m NOT IN (0, 1)
                OR (charge_off_60m IS NOT NULL AND horizon_end > snapshot_date)),
            (SELECT count(*) FROM modeling_cohort),
            (SELECT count(charge_off_60m) FROM loan_portfolio),
            (SELECT count(*) FROM typed) = (SELECT count(*) FROM loan_portfolio)
    """).fetchone()
    if invalid or not cohort or cohort != eligible or not agreement:
        raise ValueError("Portfolio or target reconciliation failed.")
    totals = db.execute("""
        SELECT count(*), count(charge_off_60m), count_if(charge_off_60m = 1)
        FROM loan_portfolio
    """).fetchone()
    dimensions = db.execute("""
        SELECT dimension, sum(records), sum(eligible_60m_records), sum(chargeoffs_60m)
        FROM portfolio_summary GROUP BY dimension
    """).fetchall()
    if not dimensions or any(tuple(row[1:]) != totals for row in dimensions):
        raise ValueError("Portfolio dimensions do not reconcile to the loan table.")


def build(source, dictionary):
    names = read_contract(source, dictionary)
    sources = {"csv": source_manifest(source), "dictionary": source_manifest(dictionary)}
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    # Stage outputs until SQL, validation and rendering all succeed.
    with TemporaryDirectory(prefix=".build-", dir=DATABASE.parent) as work_dir:
        work = Path(work_dir)
        staged_db = work / DATABASE.name
        output = work / "reports"
        output.mkdir()
        with duckdb.connect(str(staged_db), config={"threads": 4, "memory_limit": "2GB"}) as db:
            inferred = load_source(db, source)
            run_sql(db, "01_clean.sql")
            validate_release(db)
            run_sql(db, "02_target.sql")
            run_sql(db, "03_portfolio.sql")
            validate_output(db)
            fields = field_profile(db, names, inferred)
            report = write_reports(db, output, fields, sources)
            charts.render(db, output, SNAPSHOT)
            db.execute("CHECKPOINT")
        os.replace(staged_db, DATABASE)
        for artifact in output.iterdir():
            os.replace(artifact, REPORTS / artifact.name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=SOURCE_CSV)
    parser.add_argument("--dictionary", type=Path, default=SOURCE_DICTIONARY)
    args = parser.parse_args()
    report = build(args.csv, args.dictionary)
    print(f"Built {DATABASE}")
    print(f"Source: {report['duplicate_check']}")
    print(f"Target: {report['target_sensitivity']}")
    print(f"Aggregate reports: {REPORTS}")


if __name__ == "__main__":
    main()
