select
    payment_id,
    invoice_id,
    cast(payment_date as date)          as payment_date,
    cast(paid_amount as decimal(14, 2)) as paid_amount,
    paid_to_account
from {{ source('erp', 'payments') }}
