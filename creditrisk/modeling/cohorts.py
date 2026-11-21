"""Extract the frozen target and keep evaluation metadata out of features."""

from dataclasses import dataclass

import duckdb
import pandas as pd

from creditrisk.paths import DATABASE

NUMERIC = ("gross_approval", "sba_guaranteed_approval", "initial_interest_rate_pct")
CATEGORICAL = ("rate_type", "project_state", "naics_code", "processing_method",
               "business_type", "business_age", "collateral_reported", "revolving_credit")
FEATURES = NUMERIC + CATEGORICAL
TARGET = "charge_off_60m"


@dataclass(frozen=True)
class Windows:
    train_end: str
    tune_end: str
    calibration_end: str
    validation_end: str
    test_start: str = "2017-10-01"
    test_end: str = "2019-10-01"
    maturity_cutoff: str | None = None


PRIMARY = Windows("2015-10-01", "2016-10-01", "2017-04-01", "2017-10-01")
MATURE = Windows("2010-10-01", "2011-10-01", "2012-04-01", "2012-10-01",
                 maturity_cutoff="2017-10-01")


def load_cohort(database=DATABASE):
    fields = {
        "initial_interest_rate_pct": "CASE WHEN initial_interest_rate_pct > 0 THEN initial_interest_rate_pct END",
        **{field: f"{field}::VARCHAR" for field in CATEGORICAL},
    }
    features = ", ".join(f"{fields.get(field, field)} AS {field}" for field in FEATURES)
    query = f"""
        SELECT rowid AS local_record_id, first_disbursement_date, horizon_end, approval_fy,
               year(first_disbursement_date + INTERVAL '3 months') AS origination_fy,
               amount_band, term_band, naics_sector, {features}, {TARGET}
        FROM loan_portfolio
        WHERE {TARGET} IS NOT NULL
        ORDER BY rowid
    """
    with duckdb.connect(str(database), read_only=True) as db:
        return db.execute(query).fetchdf()


def features(frame):
    result = frame.loc[:, list(FEATURES)].copy()
    # Normalize pandas nullable/string representations before sklearn sees them.
    for field in CATEGORICAL:
        values = result[field].astype(object)
        result[field] = values.where(pd.notna(values), float("nan"))
    return result


def chronological_split(frame, windows=PRIMARY):
    funding = frame["first_disbursement_date"]
    train, tune, calibration, selection, test_start, test_end = (
        pd.Timestamp(value) for value in (
            windows.train_end, windows.tune_end, windows.calibration_end,
            windows.validation_end, windows.test_start, windows.test_end,
        )
    )
    mature = (frame["horizon_end"] < pd.Timestamp(windows.maturity_cutoff)
              if windows.maturity_cutoff else pd.Series(True, index=frame.index))
    masks = {
        "train": (funding < train) & mature,
        "tune": (funding >= train) & (funding < tune) & mature,
        "calibration": (funding >= tune) & (funding < calibration) & mature,
        "selection": (funding >= calibration) & (funding < selection) & mature,
        "test": (funding >= test_start) & (funding < test_end),
        "score_only": funding >= test_end,
    }
    splits = {name: frame.loc[mask] for name, mask in masks.items()}
    development = [splits[name] for name in ("train", "tune", "calibration", "selection")]
    if any(part.empty or part[TARGET].nunique() != 2 for part in development):
        raise ValueError("Each development cohort must contain both target classes.")
    periods = [*development, splits["test"]]
    if any(left.first_disbursement_date.max() >= right.first_disbursement_date.min()
           for left, right in zip(periods, periods[1:])):
        raise ValueError("Chronological split boundaries overlap.")
    return splits
