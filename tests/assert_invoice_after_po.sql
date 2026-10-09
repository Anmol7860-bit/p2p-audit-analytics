-- An invoice dated before its PO is a retrospective PO, a known control weakness
select invoice_id from {{ ref('fct_invoice') }}
where invoice_date < po_date
