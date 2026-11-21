"""Project-relative locations for source data, reports, and local model artifacts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SOURCE_CSV = RAW / "FOIA_7a_FY2010_FY2019_asof_260930.csv"
SOURCE_DICTIONARY = RAW / "7a_504_foia_data_dictionary.xlsx"
DATABASE = ROOT / "data" / "derived" / "creditrisk.duckdb"
REPORTS = ROOT / "reports"
MODELING_REPORTS = REPORTS / "modeling"
ARTIFACTS = ROOT / "artifacts" / "models"
