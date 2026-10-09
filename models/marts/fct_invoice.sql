-- Accumulating snapshot: one row per invoice, tracking its PO -> invoice -> payment lifecycle.
select
    i.invoice_id,
    i.vendor_invoice_no,
    i.vendor_id,
    i.po_id,
    po.requester_id,
    po.approver_id,
    i.posted_by_id,
    po.po_date,
    i.invoice_date,
    p.payment_date,
    po.po_amount,
    i.invoice_amount,
    p.paid_amount,
    p.paid_to_account,
    date_diff('day', po.po_date, i.invoice_date)     as days_po_to_invoice,
    date_diff('day', i.invoice_date, p.payment_date) as days_invoice_to_payment
from {{ ref('stg_invoices') }} i
join {{ ref('stg_purchase_orders') }} po using (po_id)
left join {{ ref('stg_payments') }} p using (invoice_id)
