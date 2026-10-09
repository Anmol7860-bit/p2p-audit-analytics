"""Generate a synthetic Procure-to-Pay (P2P) dataset with planted audit anomalies.

Writes raw ERP-style extracts to data/raw/ and the answer key to data/labels.csv.
The modelling + detection pipeline never reads labels.csv; it is only used to score results.
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_VENDORS, N_EMPLOYEES, N_POS = 300, 80, 25_000
APPROVAL_LIMIT = 10_000  # POs above this need a manager other than the requester
START, END = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")
CATEGORIES = {"IT Services": 9.0, "Office Supplies": 6.0, "Logistics": 8.5,
              "Consulting": 9.5, "Facilities": 7.5, "Raw Materials": 8.8}  # log-mean spend

rng = np.random.default_rng(SEED)
out = Path("data/raw")
out.mkdir(parents=True, exist_ok=True)


def bank():
    return f"IN{rng.integers(10**11, 10**12)}"


def biz_day(d):
    """Shift weekend dates to the next Monday (normal postings happen on weekdays)."""
    return d + pd.Timedelta(days=(7 - d.weekday()) % 7) if d.weekday() >= 5 else d


days = (END - START).days

vendors = pd.DataFrame({
    "vendor_id": [f"V{i:04d}" for i in range(N_VENDORS)],
    "vendor_name": [f"Vendor {i:04d} Pvt Ltd" for i in range(N_VENDORS)],
    "category": rng.choice(list(CATEGORIES), N_VENDORS),
    "country": rng.choice(["IN", "IN", "IN", "US", "UK", "SG"], N_VENDORS),
    "bank_account": [bank() for _ in range(N_VENDORS)],
    "created_at": [START - pd.Timedelta(days=int(d)) for d in rng.integers(30, 2000, N_VENDORS)],
    "is_approved": True,
})

employees = pd.DataFrame({
    "employee_id": [f"E{i:03d}" for i in range(N_EMPLOYEES)],
    "department": rng.choice(["Procurement", "Finance", "Operations", "IT", "Admin"], N_EMPLOYEES),
    "role": ["Manager" if i < 15 else "Staff" for i in range(N_EMPLOYEES)],
})
managers, staff = employees.employee_id[:15].tolist(), employees.employee_id[15:].tolist()

# --- normal purchase orders -> invoices -> payments -------------------------------------
v_idx = rng.integers(0, N_VENDORS, N_POS)
cat_mu = vendors.category.map(CATEGORIES).to_numpy()[v_idx]
po_amt = np.round(np.exp(rng.normal(cat_mu, 0.7)), 2)
# ~6% of vendors bill a fixed monthly fee (legit repeated amounts -> duplicate-test false positives)
fixed_fee = rng.random(N_VENDORS) < 0.06
po_amt = np.where(fixed_fee[v_idx], np.round(np.exp(cat_mu), -2), po_amt)
# legit round numbers & weekend work happen too -> rules are noisy
po_amt = np.where(rng.random(N_POS) < 0.04, np.round(po_amt, -3).clip(1000), po_amt)
po_dates = [biz_day(START + pd.Timedelta(days=int(d))) for d in rng.integers(0, days - 60, N_POS)]
requesters = rng.choice(staff, N_POS)
approvers = rng.choice(managers, N_POS)

pos = pd.DataFrame({
    "po_id": [f"PO{i:06d}" for i in range(N_POS)],
    "vendor_id": vendors.vendor_id.to_numpy()[v_idx],
    "requester_id": requesters,
    "approver_id": np.where(po_amt > APPROVAL_LIMIT, approvers, requesters),  # small POs self-approved
    "po_date": po_dates,
    "po_amount": po_amt,
})

inv_dates = [biz_day(d + pd.Timedelta(days=int(x))) for d, x in zip(pos.po_date, rng.integers(3, 30, N_POS))]
weekend_ok = rng.random(N_POS) < 0.02
inv_dates = [d - pd.Timedelta(days=d.weekday() - 5) if w else d for d, w in zip(inv_dates, weekend_ok)]
invoices = pd.DataFrame({
    "invoice_id": [f"INV{i:06d}" for i in range(N_POS)],
    "vendor_invoice_no": [f"{v}-{rng.integers(10**5, 10**6)}" for v in pos.vendor_id],
    "po_id": pos.po_id,
    "vendor_id": pos.vendor_id,
    "invoice_date": inv_dates,
    "invoice_amount": np.round(pos.po_amount * rng.uniform(0.97, 1.02, N_POS), 2),
    "posted_by": rng.choice(employees.query("department == 'Finance'").employee_id, N_POS),
})
labels = []


def add_invoice(po_id, vendor_id, date, amount, inv_no=None):
    i = len(invoices)
    invoices.loc[i] = [f"INV{i:06d}", inv_no or f"{vendor_id}-{rng.integers(10**5, 10**6)}",
                       po_id, vendor_id, date, amount, rng.choice(invoices.posted_by)]
    return invoices.invoice_id[i]


def add_po(vendor_id, requester, approver, date, amount):
    i = len(pos)
    pos.loc[i] = [f"PO{i:06d}", vendor_id, requester, approver, date, amount]
    return pos.po_id[i]


# --- planted anomalies ------------------------------------------------------------------
# 1. Duplicate invoice: same vendor + amount re-submitted days later with a tweaked number
for i in rng.choice(N_POS, 90, replace=False):
    src = invoices.loc[i]
    new = add_invoice(src.po_id, src.vendor_id, biz_day(src.invoice_date + pd.Timedelta(days=int(rng.integers(1, 6)))),
                      src.invoice_amount, src.vendor_invoice_no + rng.choice(["A", "-1", "/R"]))
    labels.append((new, "duplicate_invoice"))

# 2. Split purchase: one requester raises 3-4 POs to the same vendor on one day, each just
#    under the approval limit, and self-approves them all
for _ in range(40):
    v, r = rng.choice(vendors.vendor_id), rng.choice(staff)
    d = biz_day(START + pd.Timedelta(days=int(rng.integers(0, days - 60))))
    for _ in range(rng.integers(3, 5)):
        amt = round(float(rng.uniform(0.88, 0.995) * APPROVAL_LIMIT), 2)
        po = add_po(v, r, r, d, amt)
        labels.append((add_invoice(po, v, biz_day(d + pd.Timedelta(days=int(rng.integers(3, 15)))), amt), "split_purchase"))

# 3. Invoice inflated well above its PO
for i in rng.choice(N_POS, 80, replace=False):
    invoices.loc[i, "invoice_amount"] = round(invoices.invoice_amount[i] * rng.uniform(1.25, 2.5), 2)
    labels.append((invoices.invoice_id[i], "inflated_invoice"))

# 4. Ghost vendor: created and paid within days, never approved, round amounts
for _ in range(25):
    vid = f"V{len(vendors):04d}"
    d = biz_day(START + pd.Timedelta(days=int(rng.integers(30, days - 60))))
    vendors.loc[len(vendors)] = [vid, f"Vendor {vid[1:]} Enterprises", rng.choice(list(CATEGORIES)), "IN",
                                 bank(), d - pd.Timedelta(days=int(rng.integers(1, 10))), False]
    for _ in range(rng.integers(1, 4)):
        amt = float(rng.choice([25_000, 40_000, 50_000, 75_000]))
        po = add_po(vid, rng.choice(staff), rng.choice(managers), d, amt)
        labels.append((add_invoice(po, vid, biz_day(d + pd.Timedelta(days=int(rng.integers(2, 10)))), amt), "ghost_vendor"))

# 5. Self-approved large PO (segregation-of-duties breach), posted on a weekend
for i in rng.choice(np.flatnonzero(pos.po_amount[:N_POS] > APPROVAL_LIMIT), 60, replace=False):
    pos.loc[i, "approver_id"] = pos.requester_id[i]
    d = invoices.invoice_date[i]
    invoices.loc[i, "invoice_date"] = d + pd.Timedelta(days=(5 - d.weekday()) % 7)
    labels.append((invoices.invoice_id[i], "sod_breach"))

# payments: normally to the vendor master bank account
pay_lag = rng.integers(15, 60, len(invoices))
payments = pd.DataFrame({
    "payment_id": [f"PAY{i:06d}" for i in range(len(invoices))],
    "invoice_id": invoices.invoice_id,
    "payment_date": [biz_day(d + pd.Timedelta(days=int(x))) for d, x in zip(invoices.invoice_date, pay_lag)],
    "paid_amount": invoices.invoice_amount,
    "paid_to_account": invoices.vendor_id.map(vendors.set_index("vendor_id").bank_account),
})

# 6. Payment diverted to a different bank account, paid unusually fast
labelled = {i for i, _ in labels}
for i in rng.choice([i for i in range(N_POS) if invoices.invoice_id[i] not in labelled], 70, replace=False):
    payments.loc[i, "paid_to_account"] = bank()
    payments.loc[i, "payment_date"] = biz_day(invoices.invoice_date[i] + pd.Timedelta(days=int(rng.integers(0, 3))))
    labels.append((invoices.invoice_id[i], "diverted_payment"))

for name, df in [("vendors", vendors), ("employees", employees), ("purchase_orders", pos),
                 ("invoices", invoices), ("payments", payments)]:
    df.to_csv(out / f"{name}.csv", index=False)
pd.DataFrame(labels, columns=["invoice_id", "anomaly_type"]).drop_duplicates("invoice_id").to_csv("data/labels.csv", index=False)
print(f"{len(invoices):,} invoices, {len(set(labelled) | {i for i, _ in labels}):,} planted anomalies "
      f"({len(labels) / len(invoices):.1%})")
