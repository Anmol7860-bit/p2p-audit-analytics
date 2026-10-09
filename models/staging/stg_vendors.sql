select
    vendor_id,
    trim(vendor_name)         as vendor_name,
    category,
    country,
    bank_account,
    cast(created_at as date)  as created_date,
    cast(is_approved as boolean) as is_approved
from {{ source('erp', 'vendors') }}
