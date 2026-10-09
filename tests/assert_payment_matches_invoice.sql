-- Every payment should equal its invoice amount (partial / over-payments need review)
select invoice_id from {{ ref('fct_invoice') }}
where paid_amount <> invoice_amount
