"""Query the validated portfolio and frozen scores without reading raw data."""

from dataclasses import dataclass
import json
import math

import duckdb
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics import precision_recall_curve, roc_curve

from creditrisk.modeling.decisions import confusion
from creditrisk.paths import ARTIFACTS, DATABASE, MODELING_REPORTS
from creditrisk.profile import source_manifest

from .catalog import DIMENSIONS, FILTER_FIELDS, MODELS

SCORES = ARTIFACTS / "loan_scores.parquet"
FIT = SCORES.with_name("fit_manifest.json")
REPORTS = MODELING_REPORTS
SIGNATURE_FILES = ("metrics.csv", "reliability.csv", "tree_shap_importance.csv", "cohort_audit.csv",
                   "development_decisions.json", "run_summary.json")

SCORED_PORTFOLIO = """
    SELECT
        CAST(s.origination_fy AS VARCHAR) AS vintage,
        coalesce(p.project_state, 'Unknown') AS state,
        coalesce(p.naics_sector, 'Unknown') AS industry,
        p.amount_band AS size, p.term_band AS term,
        CASE p.collateral_reported WHEN true THEN 'Yes' WHEN false THEN 'No'
             ELSE 'Unknown' END AS collateral,
        CAST(s.risk_decile AS VARCHAR) AS decile, s.cohort,
        CAST(p.gross_approval AS DOUBLE) AS approved_usd, p.charge_off_60m AS outcome,
        s.logistic, s.random_forest, s.xgboost
    FROM loan_portfolio AS p
    INNER JOIN read_parquet(?) AS s ON p.rowid = s.local_record_id
    WHERE p.charge_off_60m IS NOT NULL
"""


@dataclass(frozen=True)
class Scope:
    cohort: str = "test"
    filters: tuple[tuple[str, tuple[str, ...]], ...] = ()


def release_key():
    paths = (DATABASE, SCORES, FIT, *(REPORTS / name for name in SIGNATURE_FILES))
    return tuple((path.name, (info := path.stat()).st_size, info.st_mtime_ns) for path in paths)


@st.cache_data(show_spinner=False, max_entries=3)
def release(key):
    fit = json.loads(FIT.read_text(encoding="utf-8"))
    published = json.loads((REPORTS / "development_decisions.json").read_text(encoding="utf-8"))
    summary = json.loads((REPORTS / "run_summary.json").read_text(encoding="utf-8"))
    if (fit != published or source_manifest(DATABASE) != fit["database"]
            or summary["source_database"] != fit["database"]
            or summary.get("scores") != source_manifest(SCORES)
            or summary["models"]["retrospective"]["selected_on_validation"]
            != fit["studies"]["retrospective"]["champion"]):
        raise ValueError("Score artifacts and portfolio database are from different builds.")
    with duckdb.connect(str(DATABASE), read_only=True) as db:
        eligible, snapshot = db.execute("""
            SELECT count(*), max(snapshot_date) FROM loan_portfolio WHERE charge_off_60m IS NOT NULL
        """).fetchone()
        cohort_counts = db.execute("""
            SELECT s.cohort, count(*) AS records, count(DISTINCT s.local_record_id) AS ids,
                   count(*) FILTER (WHERE p.charge_off_60m IS NULL
                       OR s.origination_fy IS DISTINCT FROM year(p.first_disbursement_date + INTERVAL '3 months')
                       OR coalesce(s.risk_decile NOT BETWEEN 1 AND 10, true)
                       OR NOT coalesce(s.logistic BETWEEN 0 AND 1, false)
                       OR NOT coalesce(s.random_forest BETWEEN 0 AND 1, false)
                       OR NOT coalesce(s.xgboost BETWEEN 0 AND 1, false)) AS invalid
            FROM read_parquet(?) s LEFT JOIN loan_portfolio p ON p.rowid = s.local_record_id
            GROUP BY s.cohort
        """, [str(SCORES)]).fetchall()
        distinct_rows = db.execute("SELECT count(DISTINCT local_record_id) FROM read_parquet(?)",
                                   [str(SCORES)]).fetchone()[0]
    audit = pd.read_csv(REPORTS / "cohort_audit.csv").query("study == 'retrospective'")
    if (sum(row[1] for row in cohort_counts) != eligible or distinct_rows != eligible
            or any(records != ids or invalid for _, records, ids, invalid in cohort_counts)
            or {name: count for name, count, _, _ in cohort_counts} != dict(zip(audit.cohort, audit.records))):
        raise ValueError("Saved scores do not reconcile to the eligible cohort.")
    return {"fit": fit, "summary": summary, "snapshot": snapshot.isoformat(),
            "champion": fit["studies"]["retrospective"]["champion"]}


@st.cache_data(show_spinner=False, max_entries=56)
def _query(key, sql, params=()):
    with duckdb.connect(str(DATABASE), read_only=True, config={"threads": 4}) as db:
        return db.execute(sql, list(params)).fetchdf()


def conditions(scope):
    where, parameters = [], []
    if scope.cohort != "all":
        where.append("cohort = ?")
        parameters.append(scope.cohort)
    for field, values in scope.filters:
        if field not in FILTER_FIELDS:
            raise ValueError(f"Unknown portfolio filter {field}")
        if values:
            where.append(f"{field} IN (SELECT unnest(?))")
            parameters.append(list(values))
    return ("WHERE " + " AND ".join(where) if where else ""), tuple(parameters)


def aggregates(key, scope, dimensions, model, stress=None):
    if model not in MODELS or not dimensions or any(name not in DIMENSIONS for name in dimensions):
        raise ValueError("Unknown model or portfolio grouping.")
    where, filters = conditions(scope)
    groups = {name: "'All eligible'" if name == "portfolio" else name for name in dimensions}
    segments = ", ".join(f"('{name}', {expression})" for name, expression in groups.items())
    stress_fields = ""
    factors = ()
    if stress is not None:
        moderate, severe = stress
        if not all(math.isfinite(x) for x in stress) or not 1 <= moderate <= severe:
            raise ValueError("Stress multipliers must satisfy 1.0 ≤ moderate ≤ severe.")
        stress_fields = """
            , sum(approved_usd * probability) / nullif(sum(approved_usd), 0) AS baseline
            , sum(approved_usd * least(probability * ?, 1.0)) / nullif(sum(approved_usd), 0) AS moderate
            , sum(approved_usd * least(probability * ?, 1.0)) / nullif(sum(approved_usd), 0) AS severe
        """
        factors = stress
    return _query(key, f"""
        WITH scored AS ({SCORED_PORTFOLIO}),
             filtered AS (SELECT *, CAST({model} AS DOUBLE) AS probability FROM scored {where})
        SELECT dimension, segment, count(*) AS records, sum(approved_usd) AS approved_usd,
               sum(outcome) AS events, avg(outcome) AS observed_rate,
               avg(probability) AS predicted_rate, sum(probability) AS expected_events
               {stress_fields}
        FROM filtered CROSS JOIN LATERAL (VALUES {segments}) AS groups(dimension, segment)
        GROUP BY dimension, segment ORDER BY dimension, segment
    """, (str(SCORES), *filters, *factors))


def filter_options(key, model):
    data = aggregates(key, Scope("all"), tuple(FILTER_FIELDS), model)
    options = {field: data.loc[data.dimension.eq(field), "segment"].tolist() for field in FILTER_FIELDS}
    for field in ("size", "term"):
        options[field] = sorted(options[field], key=lambda value: BAND_ORDER.get(value, 99))
    return options


BAND_ORDER = {
    "Under $50k": 0, "$50k to <$150k": 1, "$150k to <$500k": 2, "$500k to <$1m": 3,
    "$1m and above": 4, "1–60": 0, "61–120": 1, "121–240": 2, "241+": 3,
}


@st.cache_data(show_spinner=False, max_entries=20)
def report(key, name):
    if name not in SIGNATURE_FILES or not name.endswith(".csv"):
        raise ValueError("Unknown dashboard report.")
    return pd.read_csv(REPORTS / name)


@st.cache_data(show_spinner=False, max_entries=3)
def model_scores(key, cohort):
    if cohort not in {"test", "selection"}:
        raise ValueError("Model evaluation requires a validation or test cohort.")
    return _query(key, f"""
        WITH scored AS ({SCORED_PORTFOLIO})
        SELECT outcome, logistic, random_forest, xgboost FROM scored WHERE cohort = ?
    """, (str(SCORES), cohort))


def _reduce_curve(x, y, max_points=650):
    if len(x) <= max_points:
        return x, y
    indices = np.unique(np.linspace(0, len(x) - 1, max_points).astype(int))
    return x[indices], y[indices]


@st.cache_data(show_spinner=False, max_entries=5)
def discrimination(key, cohort):
    saved = model_scores(key, cohort)
    result = {}
    for model in MODELS:
        fpr, tpr, _ = roc_curve(saved.outcome, saved[model])
        precision, recall, _ = precision_recall_curve(saved.outcome, saved[model])
        result[model] = {"roc": _reduce_curve(fpr, tpr), "pr": _reduce_curve(recall, precision)}
    return result


def model_diagnostics(key, cohort, model, threshold):
    saved = model_scores(key, cohort)
    return confusion(saved.outcome.to_numpy(), saved[model].to_numpy(), threshold)
