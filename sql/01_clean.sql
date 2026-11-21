-- raw_unique contains exact full-row source groups. It is temporary.
CREATE TEMP MACRO clean(x) AS nullif(trim(x), '');
CREATE TEMP MACRO iso_date(x) AS try_strptime(clean(x), '%Y-%m-%d')::DATE;

CREATE TEMP TABLE typed AS
SELECT
    source_copies,
    iso_date(AsOfDate) AS snapshot_date,
    upper(clean(Program)) AS program,
    iso_date(ApprovalDate) AS approval_date,
    try_cast(clean(ApprovalFY) AS SMALLINT) AS approval_fy,
    iso_date(FirstDisbursementDate) AS first_disbursement_date,
    iso_date(PaidInFullDate) AS paid_in_full_date,
    iso_date(ChargeOffDate) AS charge_off_date,
    clean(AsOfDate) IS NOT NULL AND snapshot_date IS NULL AS invalid_snapshot_date,
    clean(ApprovalDate) IS NOT NULL AND approval_date IS NULL AS invalid_approval_date,
    clean(FirstDisbursementDate) IS NOT NULL AND first_disbursement_date IS NULL AS invalid_disbursement_date,
    clean(PaidInFullDate) IS NOT NULL AND paid_in_full_date IS NULL AS invalid_paid_date,
    clean(ChargeOffDate) IS NOT NULL AND charge_off_date IS NULL AS invalid_charge_off_date,
    try_cast(clean(GrossApproval) AS DECIMAL(18,2)) AS gross_approval,
    try_cast(clean(SBAGuaranteedApproval) AS DECIMAL(18,2)) AS sba_guaranteed_approval,
    try_cast(clean(GrossChargeOffAmount) AS DECIMAL(18,2)) AS gross_charge_off_amount,
    CASE WHEN regexp_full_match(clean(TermInMonths), '[0-9]+(\.0+)?')
         THEN try_cast(clean(TermInMonths) AS INTEGER) END AS term_months,
    try_cast(clean(InitialInterestRate) AS DECIMAL(12,5)) AS initial_interest_rate_pct,
    CASE WHEN regexp_full_match(clean(JobsSupported), '[0-9]+(\.0+)?')
         THEN try_cast(clean(JobsSupported) AS INTEGER) END AS jobs_supported,
    upper(clean(ProjectState)) AS project_state,
    CASE WHEN regexp_full_match(clean(NaicsCode), '[0-9]{6}')
              AND clean(NaicsCode) <> '000000' THEN clean(NaicsCode) END AS naics_code,
    clean(ProcessingMethod) AS processing_method,
    upper(clean(FixedorVariableInterestInd)) AS rate_type,
    clean(BusinessType) AS business_type,
    CASE WHEN upper(clean(BusinessAge)) <> 'UNANSWERED' THEN clean(BusinessAge) END AS business_age,
    regexp_replace(upper(clean(LoanStatus)), '\s+', '', 'g') AS loan_status,
    CASE upper(clean(CollateralInd)) WHEN 'Y' THEN true WHEN 'N' THEN false END AS collateral_reported,
    CASE upper(clean(RevolverStatus))
        WHEN 'Y' THEN true WHEN '1' THEN true WHEN 'N' THEN false WHEN '0' THEN false
    END AS revolving_credit
FROM raw_unique;
