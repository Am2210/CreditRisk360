"""Render reproducible, aggregate portfolio charts."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, StrMethodFormatter

from .profile import query


def render(db, output, snapshot):
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.labelcolor": "#334155",
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.grid": True,
        "grid.alpha": 0.22,
        "axes.axisbelow": True,
    })
    cohort = query(db, """
        SELECT segment, eligible_60m_records, chargeoff_60m_pct
        FROM portfolio_summary
        WHERE dimension = 'origination_year' AND eligible_60m_records > 0
        ORDER BY segment
    """)
    fig, (rate_ax, count_ax) = plt.subplots(2, 1, sharex=True, figsize=(9.5, 6.3))
    years = [int(row["segment"]) for row in cohort]
    rate_ax.plot(years, [row["chargeoff_60m_pct"] for row in cohort], color="#14647a", marker="o")
    rate_ax.set(ylabel="Recorded charge-offs (%)", ylim=(0, None))
    rate_ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    count_ax.bar(years, [row["eligible_60m_records"] for row in cohort], color="#587897")
    count_ax.set(xlabel="Calendar year of first disbursement", ylabel="Eligible loan records")
    count_ax.set_xticks(years, labels=years, rotation=45)
    count_ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    fig.suptitle("Five-year SBA charge-off frequency by origination year", x=0.08, ha="left", weight="bold")
    fig.text(0.08, 0.02, f"SBA 7(a) approvals, FY2010–FY2019 | Snapshot {snapshot} | Eligible records only",
             color="#475569", fontsize=9)
    fig.tight_layout(rect=(0.03, 0.06, 0.98, 0.94))
    fig.savefig(output / "chargeoff_by_origination.png", dpi=170)
    plt.close(fig)

    states = query(db, """
        SELECT segment, gross_approval_usd, sba_guaranteed_approval_usd
        FROM portfolio_summary
        WHERE dimension = 'project_state' AND segment <> 'Unknown'
        ORDER BY gross_approval_usd DESC NULLS LAST, segment LIMIT 10
    """)[::-1]
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    state_labels = [row["segment"] for row in states]
    ax.barh(state_labels, [float(row["gross_approval_usd"]) / 1e9 for row in states],
            color="#c8dce7", label="Gross approval")
    ax.barh(state_labels, [float(row["sba_guaranteed_approval_usd"]) / 1e9 for row in states],
            color="#14647a", label="SBA-guaranteed approval")
    ax.set(title="Approval amounts in the 10 largest project states", xlabel="Approved amount (USD billions)",
           ylabel="Project state")
    ax.legend(loc="lower right", frameon=False)
    fig.text(0.08, 0.02, f"SBA 7(a) approvals, FY2010–FY2019 | Snapshot {snapshot} | All distinct source records",
             color="#475569", fontsize=9)
    fig.tight_layout(rect=(0.03, 0.06, 0.98, 0.98))
    fig.savefig(output / "approval_by_state.png", dpi=170)
    plt.close(fig)
