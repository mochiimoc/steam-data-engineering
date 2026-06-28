with latest as (
    select
        developer_name,
        publisher_name,
        snapshot_date,
        row_number() over (
            partition by developer_name
            order by snapshot_date desc
        ) as rn
    from {{ ref('stg_games') }}
    where developer_name is not null
        and developer_name <> ''
)

select
    {{ dbt_utils.generate_surrogate_key(['developer_name']) }} as developer_id,
    developer_name,
    publisher_name
from latest
where rn = 1
