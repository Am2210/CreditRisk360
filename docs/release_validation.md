# Release validation

## Engineering changes

- Canonical ordering of the typed portfolio now stabilizes the DuckDB row key and input order for seeded fitting. Two independent data builds returned the same ordered portfolio fingerprint. The rebuilt tree metrics and stress outputs supersede the earlier report. The cohort definition, eligibility counts, model families, and tuning rules were preserved.
- Training records artifact SHA-256 digests. Evaluation checks the fitted files before deserializing and fingerprints the resulting score Parquet. The dashboard checks the database, score file, and model-release metadata before joining the local score keys. A regression test exercises a score fingerprint mismatch.
- Python modules share project-relative paths. DuckDB now defines the NAICS sector once for portfolio, modeling, and dashboard queries. The Windows environment pins direct and transitive dependencies. Git normalizes text line endings while retaining the screenshot and chart files as binary assets.
- The public portfolio CSV omits **275 segments** under ten records. The local DuckDB view and dashboard keep the full portfolio for reconciliation. Keep detailed local exports, raw inputs, databases, fitted binaries, and loan-level scores private.

## Commands executed

The clean environment used Windows x64 Python 3.12.7. I copied source files and the two original inputs into an ignored project copy. It began without a database, model artifacts, or reports. The following commands omit the absolute workspace prefix for portability. [Saved test results](../reports/validation/test-results.txt)

The original full environment lock used below is now named `requirements-local.txt`. The root `requirements.txt` contains the Cloud runtime dependencies.

```powershell
python -m venv artifacts/release-validation/.venv
$releasePython = (Resolve-Path 'artifacts/release-validation/.venv/Scripts/python.exe').Path
& $releasePython -m pip install --only-binary=:all: -r requirements.txt --report artifacts/release-validation/install-report.json
& $releasePython -m pip check
& $releasePython -m pip freeze | Compare-Object (Get-Content requirements.txt)
python -m pyflakes app.py creditrisk tests

Push-Location artifacts/release-validation/project
$env:MPLCONFIGDIR = Join-Path (Get-Location) '.matplotlib'
$env:PYTHONUTF8 = '1'
& $releasePython --version
& $releasePython -m compileall -q app.py creditrisk tests
& $releasePython -m creditrisk.pipeline
# Repeat the build to check identical ordered portfolio content.
& $releasePython -m creditrisk.pipeline
& $releasePython -m creditrisk.modeling.train
& $releasePython -m creditrisk.modeling.evaluate
& $releasePython -m unittest discover -s tests -v
& $releasePython -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8503
Pop-Location
```

Between DuckDB rebuilds I ran this query on the closed, read-only database. Both executions returned `b2c4478ca51487d1986af278ef87933fc2cb113025499374fca9cb0017462069`.

```sql
SELECT sha256(string_agg(sha256(to_json(p)::VARCHAR), '' ORDER BY p.rowid))
FROM loan_portfolio AS p;
```

## What was verified

- Dependency and import checks, two successful data builds, full-cohort model fitting, and held-out evaluation. The score file reconciles to **477,797** eligible records, including **19,388** observed events. All **27 tests passed in 15.476 seconds**.
- Streamlit returned HTTP 200 on its loopback health endpoint. All five pages rendered in the browser. The live overview CSV returned HTTP 200 with **98 aggregate rows**, and the portfolio row reconciled to **477,797** records.
- The scenario page displayed **2.32%, 2.90%, and 4.06%** for the default multipliers. Browser captures show the [overview](screenshots/portfolio-overview.jpg) and [stress testing](screenshots/stress-testing.jpg).
- A temporary local Git index staged **70 candidate files**. Ignore rules, staged whitespace, relative Markdown links, and checks for common secret formats passed. The check did not require a remote.

## Limits of this review

Only the pinned Windows environment was exercised. The live overview download payload and automated export paths were verified. Native browser save dialogs and every export button were outside the end-to-end check. The project was assessed for local GitHub readiness. No publishing or pushing occurred.

The study measures an observed charge-off conditional on funding. It uses one later snapshot, so historic term revisions, point-in-time feature availability, linked borrowers, and protected-group performance cannot be verified. The stress scenarios are hypothetical adjustments to a probability-weighted gross approval indicator. Current balances, LGD, and EAD are unavailable.
