select employee_id, department, role, role = 'Manager' as is_manager
from {{ ref('stg_employees') }}
