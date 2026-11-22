"""Offline export of vetted portfolio and model aggregates from the frozen local release."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pandas as pd

from creditrisk.paths import DATABASE, MODELING_REPORTS

from .data import Scope, aggregates, release, release_key
from .public_data import DIRECTORY, MIN_OUTCOME, MIN_RECORDS, OTHER, PUBLIC_REPORTS, SCHEMAS, sha256


def safe(records, events):
    return records >= MIN_RECORDS and min(events, records - events) >= MIN_OUTCOME


def pool_partition(frame, *, force_pool=()):
    """Pool unsafe groups and, if needed, another group so the residual is safe."""
    kept, pooled = [], []
    for row in sorted(frame.to_dict("records"), key=lambda item: (item["records"], item["segment"])):
        target = kept if safe(row["records"], row["events"]) and row["segment"] not in force_pool else pooled
        target.append(row)
    while pooled and not safe(sum(row["records"] for row in pooled), sum(row["events"] for row in pooled)):
        if not kept:
            raise ValueError("Cannot form a safe partition.")
        pooled.append(kept.pop(0))
    if pooled:
        columns = ("records", "events", "approved_usd", "expected_events")
        total = {name: sum(row[name] for row in pooled) for name in columns if name in pooled[0]}
        kept.append({"dimension": pooled[0]["dimension"], "segment": OTHER, **total,
                     "observed_rate": total["events"] / total["records"]})
    return pd.DataFrame(kept)


def overview(key, current):
    frames = aggregates(key, Scope("all"), ("portfolio", "vintage", "industry", "state", "size", "collateral"),
                        current["champion"])
    # The original public report contains full-archive counts for these same margins.
    # Pool any newly released eligible margin whose nonzero archive remainder is small.
    names = {"industry": "naics_sector", "state": "project_state", "size": "amount_band", "collateral": "collateral"}
    with duckdb.connect(str(DATABASE), read_only=True) as db:
        full = db.execute("SELECT dimension, segment, records FROM portfolio_summary").fetchdf()
    result = []
    for dimension, rows in frames.groupby("dimension"):
        prior = full.loc[full.dimension.eq(names.get(dimension))].set_index("segment").records
        remainder = rows.segment.map(prior) - rows.records
        small = rows.loc[remainder.between(1, MIN_RECORDS - 1), "segment"]
        if not small.empty:
            # Use a single stable pool; enlarge it until its archive remainder also has support.
            mapping = dict(zip(rows.segment, remainder.fillna(0)))
            while 0 < sum(mapping[name] for name in small) < MIN_RECORDS:
                extra = rows.loc[~rows.segment.isin(small) & rows.segment.map(mapping).gt(0)]
                if extra.empty:
                    raise ValueError("Cannot safely publish the archive complement.")
                small = pd.concat([small, extra.nsmallest(1, "records").segment])
        result.append(pool_partition(rows, force_pool=set(small)))
    return pd.concat(result, ignore_index=True)


def explorer():
    segments = pd.read_csv(MODELING_REPORTS / "risk_concentration.csv", dtype={"segment": str})
    segments = segments.rename(columns={"observed_events": "events", "gross_approval_usd": "approved_usd",
                                        "expected_recorded_events": "expected_events"})
    segments["dimension"] = segments.dimension.replace(
        {"project_state": "state", "naics_sector": "industry", "amount_band": "size", "term_band": "term"})
    deciles = pd.read_csv(MODELING_REPORTS / "risk_deciles.csv").query("cohort == 'test'").rename(columns={
        "observed_events": "events", "gross_approval_usd": "approved_usd", "expected_recorded_events": "expected_events",
    })
    deciles = deciles.assign(segment=deciles.risk_decile.astype(str), dimension="decile")
    result = []
    for _, rows in pd.concat([segments, deciles], ignore_index=True).groupby("dimension"):
        published = pool_partition(rows, force_pool={"Segments under 100"})
        pooled = published.segment.eq(OTHER)
        published.loc[pooled, "predicted_rate"] = published.expected_events / published.records
        published["modeled_event_share"] = published.expected_events / published.expected_events.sum()
        result.append(published)
    return pd.concat(result, ignore_index=True)


def plot_points(calibration_bins):
    """Use the same pooled bands for curves and calibration, avoiding new thresholds."""
    result = []
    for model, frame in calibration_bins.groupby("model"):
        ranked = frame.sort_values("predicted_rate", ascending=False)
        records, events = ranked.records.cumsum(), ranked.events.cumsum()
        positives = events.iloc[-1]
        negatives = records.iloc[-1] - positives
        assert all(safe(row.records, row.events) for row in ranked.itertuples())
        result.append((model, 0, 0, 0, 1))
        points = zip((records - events) / negatives, events / positives, events / records)
        result.extend((model, step, *row) for step, row in enumerate(points, 1))
    return pd.DataFrame(result, columns=SCHEMAS["curves.csv"])

def calibration():
    rows = pd.read_csv(MODELING_REPORTS / "reliability.csv").query(
        "study == 'retrospective' and cohort == 'test' and variant == 'selected'"
    )
    output = []
    for model, frame in rows.groupby("model"):
        bins = []
        n = events = 0
        mass = 0.0
        for row in frame.sort_values("bin_low").itertuples():
            n += row.records
            events += round(row.observed_rate * row.records)
            mass += row.predicted_rate * row.records
            if safe(n, events):
                bins.append((n, events, mass))
                n = events = 0
                mass = 0.0
        if n:
            last = bins.pop()
            bins.append((last[0] + n, last[1] + events, last[2] + mass))
        output.extend((model, count, event, total / count, event / count) for count, event, total in bins)
    return pd.DataFrame(output, columns=SCHEMAS["calibration.csv"])


def build():
    key = release_key()
    current = release(key)
    thresholds = pd.read_csv(MODELING_REPORTS / "confusion_matrices.csv").query(
        "study == 'retrospective' and cohort == 'test' and rule == 'fixed_5pct'"
    )
    if (thresholds[["tn", "fp", "fn", "tp"]] < MIN_OUTCOME).any().any():
        raise ValueError("Unsupported fixed-threshold cells.")
    stress = aggregates(key, Scope("test"), ("portfolio",), current["champion"], stress=(1.25, 1.75)).iloc[0]
    bins = calibration()
    datasets = {
        "overview.csv": overview(key, current),
        "explorer.csv": explorer(),
        "curves.csv": plot_points(bins),
        "calibration.csv": bins,
        "threshold.csv": thresholds,
        "stress.csv": pd.DataFrame([
            (name, multiplier, stress[field], int(stress.records), 10_000_000)
            for name, multiplier, field in (("Baseline", 1.0, "baseline"),
                                             ("Moderate stress", 1.25, "moderate"), ("Severe stress", 1.75, "severe"))
        ], columns=SCHEMAS["stress.csv"]),
    }
    DIRECTORY.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=DIRECTORY.parent) as scratch:
        stage = Path(scratch)
        for name, frame in datasets.items():
            frame.loc[:, list(SCHEMAS[name])].to_csv(
                stage / name, index=False, float_format="%.12g", lineterminator="\n")
        manifest = {"version": 1, "snapshot": current["snapshot"], "champion": current["champion"],
                    "fit": {"features": current["fit"]["features"]},
                    "shap_sample_records": current["summary"]["explanation"]["sample_records"],
                    "checksums": {name: sha256(stage / name) for name in datasets}}
        manifest["checksums"].update({name: sha256(MODELING_REPORTS / name) for name in PUBLIC_REPORTS})
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for name in (*datasets, "manifest.json"):
            os.replace(stage / name, DIRECTORY / name)
    print(f"Generated {len(datasets)} aggregate tables at {DIRECTORY}")


if __name__ == "__main__":
    build()
