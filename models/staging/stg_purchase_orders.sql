select
    po_id,
    vendor_id,
    requester_id,
    approver_id,
    cast(po_date as date)             as po_date,
    cast(po_amount as decimal(14, 2)) as po_amount
from {{ source('erp', 'purchase_orders') }}
