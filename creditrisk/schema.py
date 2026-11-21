"""Source contract and field-level feature decisions."""

# This inventory covers the local SBA 7(a) dictionary and CSV.
FIELD_GROUPS = {
    "Approval/disbursement candidate": (
        "GrossApproval", "SBAGuaranteedApproval", "ApprovalFY", "ProcessingMethod",
        "InitialInterestRate", "FixedorVariableInterestInd", "TermInMonths",
        "NaicsCode", "ProjectState", "BusinessType", "BusinessAge",
        "RevolverStatus", "CollateralInd",
    ),
    "Cohort timing only": ("AsOfDate", "ApprovalDate", "FirstDisbursementDate"),
    "Outcome or servicing only": (
        "LoanStatus", "PaidInFullDate", "ChargeOffDate", "GrossChargeOffAmount",
        "SoldSecMrktInd", "LocationID", "BankName", "BankFDICNumber", "BankNCUANumber",
        "BankStreet", "BankCity", "BankState", "BankZip",
    ),
    "Borrower identity or granular geography omitted": (
        "BorrName", "BorrStreet", "BorrCity", "BorrState", "BorrZip",
    ),
    "Descriptive or unverified timing omitted": (
        "Program", "NaicsDescription", "FranchiseCode", "FranchiseName", "ProjectCounty",
        "SBADistrictOffice", "CongressionalDistrict", "JobsSupported",
    ),
}
FIELD_ROLES = {field: role for role, fields in FIELD_GROUPS.items() for field in fields}

TYPED_COLUMNS = {
    "AsOfDate": "snapshot_date",
    "Program": "program",
    "ApprovalDate": "approval_date",
    "ApprovalFY": "approval_fy",
    "FirstDisbursementDate": "first_disbursement_date",
    "PaidInFullDate": "paid_in_full_date",
    "ChargeOffDate": "charge_off_date",
    "GrossApproval": "gross_approval",
    "SBAGuaranteedApproval": "sba_guaranteed_approval",
    "GrossChargeOffAmount": "gross_charge_off_amount",
    "TermInMonths": "term_months",
    "InitialInterestRate": "initial_interest_rate_pct",
    "JobsSupported": "jobs_supported",
    "ProjectState": "project_state",
    "NaicsCode": "naics_code",
    "ProcessingMethod": "processing_method",
    "FixedorVariableInterestInd": "rate_type",
    "BusinessType": "business_type",
    "BusinessAge": "business_age",
    "LoanStatus": "loan_status",
    "CollateralInd": "collateral_reported",
    "RevolverStatus": "revolving_credit",
}
