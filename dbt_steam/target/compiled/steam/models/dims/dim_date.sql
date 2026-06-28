with dates as (
    select distinct snapshot_date as d
    from "steam"."main_staging"."stg_games"
    where snapshot_date is not null
)

select
    cast(strftime(d, '%Y%m%d') as integer)         as date_id,
    d                                               as date,
    cast(strftime(d, '%Y') as integer)              as year,
    cast(strftime(d, '%m') as integer)              as month,
    cast(strftime(d, '%d') as integer)              as day,
    cast(strftime(d, '%W') as integer)              as week,
    case
        when cast(strftime(d, '%m') as integer) in (12, 1, 2)  then 'winter'
        when cast(strftime(d, '%m') as integer) in (3, 4, 5)   then 'spring'
        when cast(strftime(d, '%m') as integer) in (6, 7, 8)   then 'summer'
        else 'autumn'
    end                                             as season
from dates