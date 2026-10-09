select
    cast(d as date)              as date_day,
    year(d)                      as year,
    quarter(d)                   as quarter,
    month(d)                     as month,
    strftime(d, '%b')            as month_name,
    dayofweek(d)                 as day_of_week,  -- 0 = Sunday
    dayofweek(d) in (0, 6)       as is_weekend
from generate_series(date '2023-01-01', date '2026-12-31', interval 1 day) as t(d)
