select employee_id, department, role
from {{ source('erp', 'employees') }}
