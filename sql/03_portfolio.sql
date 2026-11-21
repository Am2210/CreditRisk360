-- Approval exposure is a commitment amount, not a current balance or EAD.
CREATE OR REPLACE VIEW portfolio_summary AS
WITH groups AS (
    SELECT dimension, coalesce(segment, 'Unknown') AS segment,
        count(*) AS records,
        sum(gross_approval) AS gross_approval_usd,
        sum(sba_guaranteed_approval) AS sba_guaranteed_approval_usd,
        count(*) FILTER (WHERE loan_status = 'CHGOFF') AS snapshot_chargeoff_records,
        count(charge_off_60m) AS eligible_60m_records,
        count(*) FILTER (WHERE charge_off_60m = 1) AS chargeoffs_60m
    FROM loan_portfolio
    CROSS JOIN LATERAL (VALUES
        ('portfolio', 'All records'),
        ('origination_year', origination_year::VARCHAR),
        ('approval_fy', approval_fy::VARCHAR),
        ('project_state', project_state),
        ('naics_sector', naics_sector),
        ('naics_code', naics_code),
        ('amount_band', amount_band),
        ('term_band', term_band),
        ('collateral', CASE collateral_reported WHEN true THEN 'Yes' WHEN false THEN 'No' END),
        ('loan_status', loan_status)
    ) AS dimensions(dimension, segment)
    GROUP BY dimension, coalesce(segment, 'Unknown')
)
SELECT *,
    round(100.0 * snapshot_chargeoff_records / records, 4) AS snapshot_chargeoff_pct,
    round(100.0 * chargeoffs_60m / nullif(eligible_60m_records, 0), 4) AS chargeoff_60m_pct
FROM groups;
