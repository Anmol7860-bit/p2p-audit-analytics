select
    invoice_id,
    vendor_invoice_no,
    po_id,
    vendor_id,
    cast(invoice_date as date)             as invoice_date,
    cast(invoice_amount as decimal(14, 2)) as invoice_amount,
    posted_by                              as posted_by_id
from {{ source('erp', 'invoices') }}
