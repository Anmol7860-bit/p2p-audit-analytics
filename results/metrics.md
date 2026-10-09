# Results

Audit budget: top 500 of 25,280 invoices. Planted anomalies: 490 (1.9%).

|                  |   precision@500 |   recall@500 |   PR-AUC |
|:-----------------|----------------:|-------------:|---------:|
| rules            |           0.846 |        0.863 |    0.848 |
| isolation_forest |           0.262 |        0.267 |    0.258 |
| robust_z         |           0.608 |        0.62  |    0.657 |
| hybrid           |           0.684 |        0.698 |  nan     |

## Recall by anomaly type

| anomaly_type      |   rules |   isolation_forest |   robust_z |   hybrid |
|:------------------|--------:|-------------------:|-----------:|---------:|
| diverted_payment  |    0.8  |               0.04 |       0    |     0.71 |
| duplicate_invoice |    0.87 |               0.04 |       1    |     0.63 |
| ghost_vendor      |    0.88 |               1    |       1    |     0.8  |
| inflated_invoice  |    0.88 |               0.14 |       1    |     0.69 |
| sod_breach        |    0.93 |               0.43 |       0.02 |     0.8  |
| split_purchase    |    0.85 |               0.26 |       0.59 |     0.65 |

## Blind-spot test (recall when the pattern's own rule is removed)

|                   |   rules only |   hybrid |
|:------------------|-------------:|---------:|
| diverted_payment  |          0   |     0    |
| duplicate_invoice |          0   |     0.17 |
| ghost_vendor      |          0.2 |     0.94 |
| inflated_invoice  |          0   |     0.99 |
| sod_breach        |          0   |     0.02 |
| split_purchase    |          0   |     0.55 |

## Most common alert drivers in the review sample

| top_driver              |   alerts |
|:------------------------|---------:|
| dup_same_amount_7d      |      114 |
| po_to_limit_ratio       |       82 |
| same_day_po_count       |       76 |
| invoice_to_po_ratio     |       55 |
| is_weekend              |       45 |
| amount_vs_vendor_median |       44 |
| is_round_amount         |       42 |
| days_invoice_to_payment |       37 |
| is_self_approved        |        3 |
| log_amount              |        2 |
