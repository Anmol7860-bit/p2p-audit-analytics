"""Score every invoice for audit risk, then evaluate against the planted answer key.

Approaches, compared at a fixed audit budget (how many invoices an auditor can review):
  rules             classic audit tests from the dbt feature mart (count of red flags)
  isolation_forest  standard unsupervised ML baseline
  robust_z          explainable outlier score: worst feature's distance from normal, in robust SDs
  hybrid            80% of budget = flagged invoices ranked by rule hits ("known risks"),
                    20% reserved for the most unusual *unflagged* invoices ("unknown risks")
No method sees the labels; data/labels.csv is only read in the evaluation section.
"""
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

AUDIT_BUDGET = 500   # invoices reviewed, ~2% of population
EXPLORE_SHARE = 0.2  # share of budget reserved for ML-only finds
FEATURES = ["log_amount", "amount_vs_vendor_median", "invoice_to_po_ratio", "dup_same_amount_7d",
            "same_day_po_count", "po_to_limit_ratio", "is_self_approved", "vendor_age_days",
            "vendor_invoice_count", "days_po_to_invoice", "days_invoice_to_payment", "is_weekend",
            "is_round_amount"]

out = Path("results")
out.mkdir(exist_ok=True)
con = duckdb.connect("p2p.duckdb")
# shuffle once so ties are broken randomly, not by file order
df = con.sql("select * from mart_invoice_risk_features order by invoice_id").df().sample(frac=1, random_state=0).reset_index(drop=True)
flags = [c for c in df if c.startswith("flag_")]
X = df[FEATURES]

df["rules_score"] = df[flags].sum(axis=1)
df["isolation_forest_score"] = -IsolationForest(n_estimators=300, random_state=42).fit(X).score_samples(X)

# robust z: |x - median| / (1.4826 * MAD); binary/low-variance features (MAD = 0) fall back to SD
dev = (X - X.median()).abs()
z = (dev / (1.4826 * dev.median()).replace(0, np.nan)).fillna(dev / X.std())
df["robust_z_score"] = z.max(axis=1)
df["top_driver"] = z.idxmax(axis=1)  # which feature made this invoice unusual -> explains every alert


def hybrid_pick(rules):
    """Indices an auditor would review: known-risk queue + explore queue."""
    known = rules[rules > 0].nlargest(int(AUDIT_BUDGET * (1 - EXPLORE_SHARE))).index
    explore = df.robust_z_score[rules == 0].nlargest(AUDIT_BUDGET - len(known)).index
    return known.append(explore)


picked = {m: df[f"{m}_score"].nlargest(AUDIT_BUDGET).index for m in ["rules", "isolation_forest", "robust_z"]}
picked["hybrid"] = hybrid_pick(df.rules_score)

df["in_review_sample"] = df.index.isin(picked["hybrid"])
con.sql("create or replace table ml_invoice_risk_scores as select invoice_id, rules_score, "
        "isolation_forest_score, robust_z_score, top_driver, in_review_sample from df")

# --- evaluation (labels are only touched here) -------------------------------------------
labels = pd.read_csv("data/labels.csv")
df = df.merge(labels, on="invoice_id", how="left")
df["is_anomaly"] = df.anomaly_type.notna()
n_by_type = labels.anomaly_type.value_counts().sort_index()

metrics = pd.DataFrame({m: {
    f"precision@{AUDIT_BUDGET}": df.is_anomaly[idx].mean(),
    f"recall@{AUDIT_BUDGET}": df.is_anomaly[idx].sum() / len(labels),
    "PR-AUC": average_precision_score(df.is_anomaly, df[f"{m}_score"]) if m != "hybrid" else np.nan,
} for m, idx in picked.items()}).T.round(3)

recall_by_type = pd.DataFrame({m: df.anomaly_type[idx].value_counts().reindex(n_by_type.index, fill_value=0) / n_by_type
                               for m, idx in picked.items()}).round(2)

# blind-spot test: delete the rule written for each pattern, as if nobody had thought of it yet
RULE_FOR = {"diverted_payment": "flag_bank_mismatch", "duplicate_invoice": "flag_duplicate",
            "ghost_vendor": "flag_unapproved_vendor", "inflated_invoice": "flag_over_po",
            "sod_breach": "flag_sod_breach", "split_purchase": "flag_split_purchase"}
blind = pd.DataFrame({t: {
    "rules only": (df.anomaly_type[(df.rules_score - df[r]).nlargest(AUDIT_BUDGET).index] == t).sum() / n_by_type[t],
    "hybrid": (df.anomaly_type[hybrid_pick(df.rules_score - df[r])] == t).sum() / n_by_type[t],
} for t, r in RULE_FOR.items()}).T.round(2)

print(metrics, "\n\nRecall by anomaly type:\n", recall_by_type, "\n\nBlind-spot test:\n", blind)

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
recall_by_type.plot.barh(ax=axes[0], width=0.8, color=["#9aa5b1", "#c4b5fd", "#3b82f6", "#d97706"])
blind.plot.barh(ax=axes[1], width=0.7, color=["#9aa5b1", "#d97706"])
axes[0].set_title("Known patterns: share caught in review sample")
axes[1].set_title("Unknown patterns: the pattern's own rule removed")
for ax in axes:
    ax.set_xlim(0, 1.05)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=4, frameon=False)
axes[0].set_ylabel("")
plt.tight_layout()
plt.savefig(out / "recall_by_type.png", dpi=150)

cols = ["invoice_id", "vendor_id", "invoice_date", "invoice_amount", "rules_score", "robust_z_score", "top_driver"]
df.loc[picked["hybrid"], cols].to_csv(out / "review_sample.csv", index=False)
(out / "metrics.md").write_text(
    f"# Results\n\nAudit budget: top {AUDIT_BUDGET} of {len(df):,} invoices. "
    f"Planted anomalies: {len(labels)} ({df.is_anomaly.mean():.1%}).\n\n"
    f"{metrics.to_markdown()}\n\n## Recall by anomaly type\n\n{recall_by_type.to_markdown()}\n\n"
    f"## Blind-spot test (recall when the pattern's own rule is removed)\n\n{blind.to_markdown()}\n\n"
    f"## Most common alert drivers in the review sample\n\n"
    f"{df.top_driver[picked['hybrid']].value_counts().to_frame('alerts').to_markdown()}\n")
