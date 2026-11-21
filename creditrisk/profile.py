"""Write aggregate-only source and transformation diagnostics."""

from csv import DictWriter
from hashlib import file_digest
from pathlib import Path
import json

from .schema import FIELD_ROLES, TYPED_COLUMNS


def query(db, sql):
    result = db.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def csv_report(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_manifest(path: Path):
    with path.open("rb") as handle:
        sha256 = file_digest(handle, "sha256").hexdigest()
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256}


def field_profile(db, names, inferred_types):
    # The source contract has been checked before constructing these identifiers.
    expressions = [
        f"""coalesce(sum(source_copies) FILTER (WHERE clean("{name}") IS NULL), 0)"""
        for name in names
    ]
    missing_counts = db.execute("SELECT " + ", ".join(expressions) + " FROM raw_unique").fetchone()
    types = {row[0]: row[1] for row in db.execute("DESCRIBE typed").fetchall()}
    logical_missing = db.execute(
        "SELECT " + ", ".join(f"count(*) - count({name})" for name in TYPED_COLUMNS.values())
        + " FROM typed"
    ).fetchone()
    transformed_counts = dict(zip(TYPED_COLUMNS, logical_missing))
    total = db.execute("SELECT sum(source_copies) FROM raw_unique").fetchone()[0]
    return [
        {
            "source_field": name,
            "ingestion_type": "VARCHAR",
            "sample_inferred_type": inferred_types[name],
            "source_blank_rows": missing,
            "source_blank_pct": round(100 * missing / total, 4),
            "typed_field": TYPED_COLUMNS.get(name),
            "typed_type": types.get(TYPED_COLUMNS.get(name)),
            "typed_null_records_after_dedup": transformed_counts.get(name),
            "feature_decision": FIELD_ROLES[name],
        }
        for name, missing in zip(names, missing_counts)
    ]


def coverage(db):
    fields = {
        "snapshot_date": "invalid_snapshot_date",
        "approval_date": "invalid_approval_date",
        "first_disbursement_date": "invalid_disbursement_date",
        "paid_in_full_date": "invalid_paid_date",
        "charge_off_date": "invalid_charge_off_date",
    }
    return [
        {"field": field, **query(db, f"""
            SELECT min({field}) AS earliest, max({field}) AS latest,
                   count({field}) AS parsed_records, count_if({invalid}) AS invalid_records,
                   count_if({field} IS NULL AND NOT {invalid}) AS blank_records
            FROM typed
        """)[0]}
        for field, invalid in fields.items()
    ]


def findings(db):
    predicates = {
        "first_disbursement_before_approval": "first_disbursement_date < approval_date",
        "first_disbursement_after_snapshot": "first_disbursement_date > snapshot_date",
        "chargeoff_before_first_disbursement": "charge_off_date < first_disbursement_date",
        "chargeoff_after_snapshot": "charge_off_date > snapshot_date",
        "payoff_before_first_disbursement": "paid_in_full_date < first_disbursement_date",
        "payoff_after_snapshot": "paid_in_full_date > snapshot_date",
        "chargeoff_status_missing_date": "loan_status = 'CHGOFF' AND charge_off_date IS NULL",
        "chargeoff_date_without_chargeoff_status": "loan_status <> 'CHGOFF' AND charge_off_date IS NOT NULL",
        "positive_chargeoff_amount_without_chargeoff_status": "loan_status <> 'CHGOFF' AND gross_charge_off_amount > 0",
        "chargeoff_status_nonpositive_or_missing_amount": "loan_status = 'CHGOFF' AND coalesce(gross_charge_off_amount, 0) <= 0",
        "paid_status_missing_date": "loan_status = 'PIF' AND paid_in_full_date IS NULL",
        "paid_date_without_paid_status": "loan_status <> 'PIF' AND paid_in_full_date IS NOT NULL",
        "both_outcome_dates_present": "charge_off_date IS NOT NULL AND paid_in_full_date IS NOT NULL",
        "closed_or_undisbursed_status_with_disbursement": "loan_status IN ('CANCLD', 'COMMIT') AND first_disbursement_date IS NOT NULL",
        "approval_nonpositive": "gross_approval <= 0",
        "guarantee_outside_approval": "sba_guaranteed_approval < 0 OR sba_guaranteed_approval > gross_approval",
        "term_nonpositive": "term_months <= 0",
        "initial_rate_nonpositive": "initial_interest_rate_pct <= 0",
        "approval_fiscal_year_mismatch": "approval_fy <> year(approval_date) + (month(approval_date) >= 10)::INT",
        "eligible_chargeoff_after_horizon": "charge_off_60m = 0 AND loan_status = 'CHGOFF'",
        "eligible_payoff_before_horizon": "charge_off_60m = 0 AND paid_in_full_date < horizon_end",
    }
    expressions = ", ".join(f"count_if({expr}) AS {name}" for name, expr in predicates.items())
    return query(db, f"SELECT {expressions} FROM loan_portfolio")[0]


def write_reports(db, output, fields, sources):
    dates = coverage(db)
    csv_report(output / "field_profile.csv", fields)
    csv_report(output / "date_coverage.csv", dates)
    csv_report(output / "portfolio_summary.csv", query(db, """
        SELECT * FROM portfolio_summary WHERE records >= 10 ORDER BY dimension, segment
    """))
    populations = query(db, """
        SELECT target_eligibility, loan_status, charge_off_60m, count(*) AS records
        FROM loan_portfolio
        GROUP BY ALL ORDER BY ALL
    """)
    csv_report(output / "target_by_status.csv", populations)
    sensitivity = query(db, """
        SELECT
            count(charge_off_60m) AS base_eligible,
            count_if(charge_off_60m = 1) AS positives,
            count_if(charge_off_60m IS NOT NULL AND loan_status = 'EXEMPT') AS exempt_negatives,
            count_if(charge_off_60m IS NOT NULL AND loan_status IN ('PIF', 'CHGOFF')) AS terminal_only_eligible,
            count_if(charge_off_60m IS NOT NULL AND source_copies = 1) AS singleton_eligible,
            count_if(charge_off_60m = 1 AND source_copies = 1) AS singleton_positives
        FROM loan_portfolio
    """)[0]
    report = {
        "sources": sources,
        "duplicate_check": query(db, """
            SELECT sum(source_copies) AS source_rows, count(*) AS distinct_source_rows,
                   count_if(source_copies > 1) AS duplicate_groups,
                   sum(source_copies - 1) AS excess_exact_duplicate_rows
            FROM loan_portfolio
        """)[0],
        "duplicates_by_normalized_status": query(db, """
            SELECT loan_status, count(*) AS duplicate_groups,
                   sum(source_copies - 1) AS excess_exact_duplicate_rows
            FROM loan_portfolio WHERE source_copies > 1 GROUP BY ALL ORDER BY ALL
        """),
        "source_categories": {
            name: query(db, f"""
                SELECT "{name}" AS raw_value, sum(source_copies) AS records
                FROM raw_unique GROUP BY 1 ORDER BY 2 DESC, 1
            """)
            for name in ("Program", "AsOfDate", "LoanStatus", "RevolverStatus", "CollateralInd",
                         "SoldSecMrktInd", "FixedorVariableInterestInd", "ProcessingMethod", "BusinessAge")
        },
        "date_coverage": dates,
        "quality_checks_nonexclusive": findings(db),
        "target_by_status": populations,
        "target_sensitivity": sensitivity,
        "portfolio_totals": query(db, "SELECT * FROM portfolio_summary WHERE dimension = 'portfolio'")[0],
        "public_summary": {"minimum_segment_records": 10, "omitted_segments": db.execute(
            "SELECT count(*) FROM portfolio_summary WHERE records < 10"
        ).fetchone()[0]},
    }
    (output / "data_quality.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    return report
