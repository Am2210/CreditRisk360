"""Render portfolio model diagnostics for the untouched test cohorts."""

import numpy as np
from sklearn.metrics import precision_recall_curve, roc_curve
from matplotlib.ticker import PercentFormatter

from creditrisk.charts import plt

COLORS = {"logistic": "#697889", "random_forest": "#936a42", "xgboost": "#14647a"}
LABELS = {"logistic": "Logistic regression", "random_forest": "Random forest", "xgboost": "XGBoost"}


def save(fig, path, caption):
    fig.text(0.05, 0.02, caption, fontsize=9, color="#45576a")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=165)
    plt.close(fig)


def draw(output, target, predictions, reliability, deciles, importance, champion, matrices):
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.2, "axes.axisbelow": True, "axes.titleweight": "bold"})
    caption = "SBA 7(a) | First disbursement FY2018–2019 | September 30, 2026 snapshot"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3))
    for name, scores in predictions.items():
        false_positive, true_positive, _ = roc_curve(target, scores)
        precision, recall, _ = precision_recall_curve(target, scores)
        axes[0].plot(false_positive, true_positive, color=COLORS[name], label=LABELS[name])
        axes[1].plot(recall, precision, color=COLORS[name], label=LABELS[name])
    axes[0].plot([0, 1], [0, 1], "--", color="0.65", label="No discrimination")
    axes[1].axhline(target.mean(), linestyle="--", color="0.65", label="Event prevalence")
    for ax, title, x, y in zip(axes, ("ROC curve", "Precision–recall curve"),
                               ("False positive rate", "Recall"), ("True positive rate", "Precision")):
        ax.set(title=title, xlabel=x, ylabel=y, xlim=(0, 1), ylim=(0, 1))
        ax.legend(frameon=False, fontsize=8)
    save(fig, output / "discrimination.png", caption)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3))
    chosen = reliability[(reliability["study"] == "retrospective") & (reliability["cohort"] == "test")
                         & (reliability["variant"] == "selected") & (reliability["records"] >= 25)]
    extent = float(max(chosen["predicted_rate"].max(), chosen["observed_rate"].max())) * 1.05
    axes[0].plot([0, extent], [0, extent], "--", color="0.6", label="Perfect calibration")
    for name, rows in chosen.groupby("model"):
        axes[0].plot(rows["predicted_rate"], rows["observed_rate"], "o-", ms=3, color=COLORS[name], label=LABELS[name])
    axes[0].set(title="Test reliability · bins with 25+ records", xlabel="Mean predicted probability",
                ylabel="Observed frequency", xlim=(0, extent), ylim=(0, extent))
    axes[0].legend(frameon=False, fontsize=8)
    test_deciles = deciles[deciles["cohort"] == "test"]
    axes[1].plot(test_deciles["risk_decile"], test_deciles["observed_rate"], "o-", label="Observed", color="#14647a")
    axes[1].plot(test_deciles["risk_decile"], test_deciles["predicted_rate"], "s--", label="Predicted", color="#936a42")
    axes[1].set(title=f"{LABELS[champion]} · test risk groups", xlabel="Risk decile (10 = highest)",
                ylabel="Five-year frequency", xticks=range(1, 11))
    axes[1].legend(frameon=False)
    for ax in axes:
        ax.yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].xaxis.set_major_formatter(PercentFormatter(1))
    save(fig, output / "calibration_and_deciles.png", caption)

    fig, ax = plt.subplots(figsize=(8.9, 5.2))
    ranked = importance.iloc[::-1]
    ax.barh(ranked["feature"].str.replace("_", " "), ranked["mean_abs_shap_margin"], color=COLORS["xgboost"])
    ax.set(title="XGBoost feature contributions", xlabel="Mean absolute Tree SHAP contribution (raw log-odds)")
    save(fig, output / "xgboost_tree_shap.png", caption + " | Random test sample")

    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    for ax, name, title in zip(axes, ("fixed_5pct", "base_validation_threshold"),
                               ("Fixed 5% threshold", "Cost threshold selected on validation")):
        row = matrices[name]
        grid = np.array([[row["tn"], row["fp"]], [row["fn"], row["tp"]]])
        shading = grid / grid.sum(axis=1, keepdims=True)
        ax.imshow(shading, cmap="Blues", vmin=0, vmax=1)
        for (i, j), value in np.ndenumerate(grid):
            ax.text(j, i, f"{value:,}", ha="center", va="center",
                    color="white" if shading[i, j] > 0.55 else "#162436", weight="bold")
        ax.set(title=f"{title}\nDecision threshold {row['threshold']:.1%}",
               xlabel="Predicted class", ylabel="Actual class", xticks=[0, 1], yticks=[0, 1])
        ax.grid(False)
    save(fig, output / "test_confusion_matrices.png", f"{LABELS[champion]} | " + caption)
