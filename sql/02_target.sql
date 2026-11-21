CREATE OR REPLACE TABLE loan_portfolio AS
WITH dates AS (
    SELECT *,
        year(first_disbursement_date) AS origination_year,
        (first_disbursement_date + INTERVAL '60 months')::DATE AS horizon_end,
        CASE
            WHEN left(naics_code, 2) IN ('31', '32', '33') THEN '31-33'
            WHEN left(naics_code, 2) IN ('44', '45') THEN '44-45'
            WHEN left(naics_code, 2) IN ('48', '49') THEN '48-49'
            ELSE left(naics_code, 2)
        END AS naics_sector,
        CASE
            WHEN gross_approval IS NULL OR gross_approval <= 0 THEN 'Unknown / invalid'
            WHEN gross_approval < 50000 THEN 'Under $50k'
            WHEN gross_approval < 150000 THEN '$50k to <$150k'
            WHEN gross_approval < 500000 THEN '$150k to <$500k'
            WHEN gross_approval < 1000000 THEN '$500k to <$1m'
            ELSE '$1m and above'
        END AS amount_band,
        CASE
            WHEN term_months IS NULL OR term_months <= 0 THEN 'Unknown / invalid'
            WHEN term_months <= 60 THEN '1–60'
            WHEN term_months <= 120 THEN '61–120'
            WHEN term_months <= 240 THEN '121–240'
            ELSE '241+'
        END AS term_band
    FROM typed
), eligibility AS (
    SELECT *,
        CASE
            WHEN snapshot_date IS NULL THEN 'missing_or_invalid_snapshot'
            WHEN loan_status IN ('CANCLD', 'COMMIT') THEN 'cancelled_or_undisbursed'
            WHEN invalid_disbursement_date THEN 'invalid_first_disbursement'
            WHEN first_disbursement_date IS NULL THEN 'missing_first_disbursement'
            WHEN approval_date IS NULL OR first_disbursement_date < approval_date
                OR first_disbursement_date > snapshot_date THEN 'inconsistent_origination_date'
            WHEN horizon_end > snapshot_date THEN 'incomplete_60m_followup'
            WHEN loan_status IS NULL OR loan_status NOT IN ('CHGOFF', 'PIF', 'EXEMPT')
                THEN 'unknown_status'
            WHEN invalid_charge_off_date OR invalid_paid_date THEN 'invalid_outcome_date'
            WHEN charge_off_date < first_disbursement_date OR charge_off_date > snapshot_date
                OR paid_in_full_date < first_disbursement_date OR paid_in_full_date > snapshot_date
                THEN 'outcome_date_outside_observation'
            WHEN loan_status = 'CHGOFF' AND charge_off_date IS NULL THEN 'chargeoff_date_missing'
            WHEN loan_status = 'PIF' AND paid_in_full_date IS NULL THEN 'payoff_date_missing'
            WHEN (loan_status <> 'CHGOFF' AND (charge_off_date IS NOT NULL OR gross_charge_off_amount > 0))
                OR (loan_status <> 'PIF' AND paid_in_full_date IS NOT NULL) THEN 'status_outcome_conflict'
            ELSE 'eligible'
        END AS target_eligibility
    FROM dates
)
SELECT *,
    CASE WHEN target_eligibility = 'eligible'
         THEN coalesce(charge_off_date BETWEEN first_disbursement_date AND horizon_end, false)::TINYINT
    END AS charge_off_60m
FROM eligibility
-- Row order determines the local join key and seeded estimator sampling.
-- Ties across every retained field are indistinguishable to downstream code.
ORDER BY ALL;

-- Explicit feature allowlist for a future funded-loan study.
-- charge_off_60m is the response column. Every other column is an allowlisted candidate.
CREATE OR REPLACE VIEW modeling_cohort AS
SELECT approval_fy, gross_approval, sba_guaranteed_approval,
       CASE WHEN initial_interest_rate_pct > 0 THEN initial_interest_rate_pct END AS initial_interest_rate_pct,
       rate_type, CASE WHEN term_months > 0 THEN term_months END AS term_months,
       project_state, naics_code, processing_method, business_type,
       business_age, collateral_reported, revolving_credit, charge_off_60m
FROM loan_portfolio
WHERE charge_off_60m IS NOT NULL;
