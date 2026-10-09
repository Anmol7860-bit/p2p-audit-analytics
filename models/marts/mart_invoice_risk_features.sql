-- One row per invoice with audit-test flags and numeric features for anomaly detection.
{% set limit = var('approval_limit') %}

with f as (
    select f.*, v.master_bank_account, v.is_approved as vendor_is_approved, v.created_date as vendor_created_date
    from {{ ref('fct_invoice') }} f
    join {{ ref('dim_vendor') }} v using (vendor_id)
),

vendor_baseline as (
    select vendor_id, median(invoice_amount) as vendor_median_amount, count(*) as vendor_invoice_count
    from f group by vendor_id
),

-- other invoices from the same vendor, same amount, within 7 days
duplicates as (
    select a.invoice_id, count(b.invoice_id) as dup_same_amount_7d
    from f a
    left join f b
      on a.vendor_id = b.vendor_id
     and a.invoice_amount = b.invoice_amount
     and a.invoice_id <> b.invoice_id
     and abs(date_diff('day', a.invoice_date, b.invoice_date)) <= 7
    group by a.invoice_id
),

-- POs raised by the same requester to the same vendor on the same day
same_day_pos as (
    select requester_id, vendor_id, po_date, count(*) as same_day_po_count
    from {{ ref('stg_purchase_orders') }}
    group by all
)

select
    f.invoice_id,
    f.vendor_id,
    f.invoice_date,
    f.invoice_amount,

    -- rule-based audit tests (0/1)
    (d.dup_same_amount_7d > 0)::int                                               as flag_duplicate,
    (s.same_day_po_count >= 3 and f.po_amount between {{ limit }} * 0.85 and {{ limit }})::int as flag_split_purchase,
    (f.invoice_amount > f.po_amount * 1.10)::int                                  as flag_over_po,
    (not f.vendor_is_approved)::int                                               as flag_unapproved_vendor,
    (f.requester_id = f.approver_id and f.po_amount > {{ limit }})::int           as flag_sod_breach,
    (f.paid_to_account <> f.master_bank_account)::int                             as flag_bank_mismatch,

    -- numeric features for the ML model
    ln(f.invoice_amount)                                                          as log_amount,
    f.invoice_amount / b.vendor_median_amount                                     as amount_vs_vendor_median,
    f.invoice_amount / f.po_amount                                                as invoice_to_po_ratio,
    d.dup_same_amount_7d,
    s.same_day_po_count,
    f.po_amount / {{ limit }}                                                     as po_to_limit_ratio,
    (f.requester_id = f.approver_id)::int                                         as is_self_approved,
    date_diff('day', f.vendor_created_date, f.invoice_date)                       as vendor_age_days,
    b.vendor_invoice_count,
    f.days_po_to_invoice,
    f.days_invoice_to_payment,
    dt.is_weekend::int                                                            as is_weekend,
    (f.invoice_amount % 1000 = 0)::int                                            as is_round_amount
from f
join vendor_baseline b using (vendor_id)
join duplicates d using (invoice_id)
join same_day_pos s using (requester_id, vendor_id, po_date)
join {{ ref('dim_date') }} dt on dt.date_day = f.invoice_date
