# Streamlit Community Cloud deployment

Use the existing **Am2210/CreditRisk360** repository, branch **main**, entry point **app.py**, and **Python 3.12** in Advanced settings. The public app requires **no runtime secrets, data credentials, or external API calls**. The deploying account still needs access to authorize the GitHub repository in Community Cloud. Keep Cloud-managed server binding. These instructions apply after the deployment changes are approved and pushed. [Streamlit deployment settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

## Runtime file audit

- **Application and dependencies.** `app.py`, `creditrisk/dashboard/`, `creditrisk/paths.py`, shared theme in `.streamlit/config.toml`, and the root `requirements.txt`. Only the local branch imports DuckDB and scikit-learn. The full training and local dashboard dependencies are pinned in `requirements-local.txt`. The Cloud dependency list has three direct Python packages. It needs no `packages.txt` or Linux system package installs.
- **New public data package.** `public_data/manifest.json` identifies the fixed snapshot and stores checksums for the public CSVs and the three reused reports. `overview.csv` contains eligible counts, historical gross approvals, and recorded events by broad margin. `explorer.csv` contains fixed holdout risk groups and segment summaries. `curves.csv` and `calibration.csv` share pooled probability bands. `threshold.csv` contains the published 5% test confusion matrices. `stress.csv` contains three portfolio-level scenario results.
- **Already public and required in Cloud.** `reports/modeling/metrics.csv`, `cohort_audit.csv`, and `tree_shap_importance.csv` supply original validation results, the cohort audit, and global SHAP. `docs/modeling_report.md` and `docs/target_and_leakage.md` support governance downloads. Other committed reports and screenshots are historical research outputs outside the public app’s runtime.
- **Full local dashboard only.** `data/derived/creditrisk.duckdb`, `artifacts/models/loan_scores.parquet`, and `artifacts/models/fit_manifest.json` are required together. The local loader also uses the committed metrics, reliability bins, SHAP and cohort reports, `development_decisions.json`, and `run_summary.json` under `reports/modeling/`. Local startup verifies the database and score fingerprints before linking them.
- **Generated locally and excluded from Git.** `data/raw/` contains the original SBA CSV and dictionary. `data/derived/` contains the private analytical database. `artifacts/models/` also contains fitted Joblib and UBJ files and individual explanation examples. The local exporter requires the validated database, scores, fit manifest, and existing reports. Training binaries and raw CSV are outside its inputs once those outputs exist.

## Public scope and disclosure

The checkout defaults to public demo when it contains no local release files. `CREDITRISK_MODE=public` explicitly selects the demo, while `CREDITRISK_MODE=local` requires the validated private release. A partial local release fails visibly so a missing artifact cannot silently substitute public results. The two modes share styling and portfolio definitions. Cached, checksummed CSV tables replace the DuckDB/Parquet join in public mode, and startup performs no training. Hashes are computed over canonical LF text to match Windows and Linux Git checkouts.

- **Executive Overview** shows eligible portfolio totals and separate fiscal-vintage, industry, state, loan-size, and collateral margins.
- **Model Lab** shows exact saved holdout metrics, a fixed 5% confusion matrix, global SHAP, and coarse ROC, precision–recall, and calibration charts. Calibration and curve counts use the same bands. The displayed metrics are from the full original holdout, independent of the binned charts. Arbitrary thresholds and individual score distributions are unavailable.
- **Risk Explorer** changes the displayed one-dimensional holdout breakdown or selects a published row from that breakdown. Risk groups always refer to the same holdout. Industry, state, loan size, and reported term cannot be intersected or excluded.
- **Stress Testing** uses the frozen holdout mix scaled to a $10 million approved-principal basis, with the published 1.00×, 1.25×, and 1.75× shocks. Each probability is capped at 100% before weighting. The figures are event indicators rather than dollar-loss estimates. Segment stress and custom multipliers remain available locally.
- **Model Governance** retains the source, target, evaluation design, model limitations, and point-in-time cautions.

New detailed release cells require at least **100 records, 10 recorded events, and 10 non-events**. Sparse segments are combined in a single pool per margin. When needed, the pool absorbs an additional group to keep the remainder above the floor. The exporter checks comparable full-archive and eligible margins for small differences. Tests check both the complement of released groups and differences between named eligible and holdout margins. Calibration tails are pooled, and curve points disclose neither exact score thresholds nor individual increments. CSV downloads pass only these fixed summaries or original aggregate validation reports. No names, addresses, ZIP codes, loan IDs, joined features, or individual probabilities are present in the new package. These controls address sparse cells and simple differencing. They do not provide a formal guarantee against all linkage with external sources or change historical GitHub reports.

## Verify and reproduce

For a public-only preview on a clean checkout, install `requirements.txt` in a fresh Python 3.12 environment:

```powershell
python -m pip install -r requirements.txt
python -m pip check
python -m unittest discover -s tests -p test_public.py -v
python -m streamlit run app.py --server.headless true --server.address 127.0.0.1
```

To regenerate the aggregate package, use the full local environment and the existing validated artifacts:

```powershell
python -m pip install -r requirements-local.txt
python -m creditrisk.dashboard.build_public
python -m unittest discover -s tests -v
```

Approve the code and public data changes before pushing to `main`. In Community Cloud, choose public sharing, confirm Python 3.12, and open the resulting URL in a signed-out browser. Check all five routes and a CSV export before using it in the showcase. [Community Cloud dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)

## Validation completed

The clean Windows Python 3.12 preview used Git-style LF CSVs and the Cloud dependency list. It had no data directory, score artifacts, secrets, DuckDB, scikit-learn, or XGBoost installed. The six public tests passed there, and all 33 tests passed in the full local workspace. All five sections rendered in the browser, and the live overview download returned HTTP 200 with 90 aggregate rows and six approved fields. The saved portfolio reconciles to 477,797 eligible records, $180.04 billion of historical approvals, and 19,388 events. Default weighted stress indicators are 2.32%, 2.90%, and 4.06%.

Linux x86-64 Python 3.12 wheels resolved and downloaded for the Cloud dependencies. A Linux runtime and Community Cloud itself were unavailable for execution during this review. The hosted startup and signed-out access remain to be verified after approval and deployment.
