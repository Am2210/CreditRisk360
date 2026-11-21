# Target definition and feature leakage

## Outcome and population

Estimate the historical frequency of an **SBA-recorded charge-off within 60 calendar months of first disbursement**, conditional on a documented funded loan in the FY2010–FY2019 7(a) release with sufficient snapshot follow-up. An SBA charge-off records when SBA charged off the loan. Default or first delinquency can occur earlier, and the release does not provide those event dates. The target measures observed charge-off incidence. It cannot estimate the timing of default, cure, or the complete servicing path.

The local workbook defines `FirstDisbursementDate` as the first funding date if available, `ChargeOffDate` as the date SBA charged off the loan, and `AsOfDate` as the date the data was recorded. Every row confirms the September 30, 2026 snapshot named in the release. [SBA FOIA release](https://data.sba.gov/dataset/7a-504-foia)

## Label rules

1. Set time zero to `FirstDisbursementDate`. Require a valid approval date and first disbursement on or after approval and on or before the snapshot. Cancelled and undisbursed records are outside the population.
2. Add 60 calendar months, including the anniversary date. DuckDB clamps a leap-day anniversary to February 28 when necessary. Require the anniversary to be on or before the snapshot for **both** classes, including known early events and payoffs.
3. Assign **1** to a consistent `CHGOFF` record with a valid charge-off date in the closed interval from first disbursement through the anniversary. Assign **0** to a consistent dated `CHGOFF` after the anniversary, a `PIF` with valid payoff chronology and no conflicting charge-off evidence, or an `EXEMPT` with no conflicting recorded outcome. Paid-in-full is a competing terminal outcome under this binary cumulative incidence definition. A charge-off amount of zero does not override an otherwise valid event date.
4. Assign **NULL** when follow-up is incomplete or the outcome is uncertain, including missing event dates for charged-off records, missing payoff dates for paid records, invalid dates, implausible chronology, unknown status and contradictions between status, dates and positive charge-off amounts. The SQL stores the first applicable reason. The independent quality checks may count the same record under multiple findings.

The dictionary describes `EXEMPT` as a disbursed loan whose status is withheld when it is outside cancelled, paid-in-full and charged-off categories. Treating a mature, consistent `EXEMPT` record as a negative assumes the extract would disclose a qualifying recorded charge-off. The snapshot does not establish continuous servicing observability or capture all historical reversals and corrections. The base rate is 4.0578% (19,388 / 477,797). Restricting to mature dated `PIF` and `CHGOFF` yields 4.4966% (19,388 / 431,168). The latter is a sensitivity check selected on terminal status and has a different denominator. Excluding all exact duplicate groups from the base yields 4.0600% (19,388 / 477,532).

## Feature leakage assessment

- **Approval-era candidates.** Approved amount and SBA guarantee, initial interest rate and rate type, term, processing method, business type and age, project state, six-digit NAICS, approval fiscal year, lender-reported collateral and revolving credit. The dictionary explicitly anchors the initial rate and processing method to approval. The remaining candidates require confirmation that the release reflects the value available at the chosen scoring date. Treat approval fiscal year as a vintage variable and assess temporal generalization.
- **Cohort metadata.** Use approval date and first disbursement date for chronology and cohorting. Use the snapshot and 60-month endpoint for observation eligibility. Exclude all four dates, derived origination year, eligibility reasons and date-quality flags from the feature view.
- **Servicing and outcomes.** Exclude `LoanStatus`, `ChargeOffDate`, `GrossChargeOffAmount`, `PaidInFullDate` and `SoldSecMrktInd`. The secondary-market flag remains set once sold, so a snapshot value can encode later activity. SBA defines the bank as the currently assigned bank. This release cannot establish approval-time lender identity from its bank fields or lender location ID. Exclude all of those fields.
- **Identity, descriptive and unverified fields.** Omit borrower name, street, city, state and ZIP. Use project state for geography. Omit franchise identifiers and names, project county, district fields, descriptive NAICS text, the constant program field and lender-estimated jobs supported. The workbook describes jobs as self-reported application estimates that SBA does not validate.

See [the complete source-field inventory](../reports/field_profile.csv) for the decision on every 7(a) field. The workbook's 504 worksheet describes a different program and has different lender fields and status codes.

## Decisions before modeling

Confirm whether the score will be produced at approval or first disbursement. This cohort is conditional on funding and is unsuitable for directly estimating risk across all applications or approvals. Check the historical availability of candidate fields and assess the EXEMPT assumption against additional snapshots or servicing data if available. Use chronological splits and account for the five-year period required for a label to mature. This release includes only loans approved through FY2019, so the later first-disbursement cohorts represent delayed funding from those approval vintages. No loan ID is supplied. Repeated borrowers or amended loans cannot be linked reliably from this release, so borrower-level split isolation is unverified.

The subsequent modeling study uses first-disbursement fiscal year for cohorting and a narrower feature allowlist. It excludes the reported term after a development-cohort leakage investigation and excludes approval fiscal year from predictors. [Modeling report](modeling_report.md)
