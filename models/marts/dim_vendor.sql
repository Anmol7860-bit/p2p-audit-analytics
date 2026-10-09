select
    vendor_id,
    vendor_name,
    category,
    country,
    bank_account as master_bank_account,
    created_date,
    is_approved
from {{ ref('stg_vendors') }}
