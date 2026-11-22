"""Read the versioned public release without importing the local analytics stack."""

from hashlib import sha256 as digest_bytes
import json

import pandas as pd
import streamlit as st

from creditrisk.paths import MODELING_REPORTS, ROOT

DIRECTORY = ROOT / "public_data"
PUBLIC_REPORTS = ("metrics.csv", "cohort_audit.csv", "tree_shap_importance.csv")
GROUP_COLUMNS = ("dimension", "segment", "records", "approved_usd", "events", "observed_rate")
SCHEMAS = {
    "overview.csv": GROUP_COLUMNS,
    "explorer.csv": (*GROUP_COLUMNS, "predicted_rate", "expected_events", "modeled_event_share"),
    "curves.csv": ("model", "step", "false_positive_rate", "recall", "precision"),
    "calibration.csv": ("model", "records", "events", "predicted_rate", "observed_rate"),
    "threshold.csv": ("model", "threshold", "tn", "fp", "fn", "tp"),
    "stress.csv": ("scenario", "multiplier", "weighted_event_indicator", "record_count", "proxy_basis_usd"),
}
MIN_RECORDS = 100
MIN_OUTCOME = 10
OTHER = "Other segments (pooled)"


def sha256(path):
    # Git normalizes CRLF in tracked text on checkout.
    return digest_bytes(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def release_key():
    paths = (DIRECTORY / "manifest.json", *(DIRECTORY / name for name in SCHEMAS),
             *(MODELING_REPORTS / name for name in PUBLIC_REPORTS))
    return tuple((path.name, (info := path.stat()).st_size, info.st_mtime_ns) for path in paths)


@st.cache_data(show_spinner=False, max_entries=2)
def load(key):
    manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != 1 or set(manifest["checksums"]) != set(SCHEMAS) | set(PUBLIC_REPORTS):
        raise ValueError("Unknown public data contract.")
    tables = {}
    for name, digest in manifest["checksums"].items():
        path = (DIRECTORY if name in SCHEMAS else MODELING_REPORTS) / name
        if sha256(path) != digest:
            raise ValueError(f"Public release checksum mismatch for {name}.")
        frame = pd.read_csv(path, dtype={"segment": str})
        if name in SCHEMAS and tuple(frame.columns) != SCHEMAS[name]:
            raise ValueError(f"Unexpected public columns in {name}.")
        tables[name] = frame
    return manifest, tables
