with latest as (
    select
        developer_name,
        publisher_name,
        snapshot_date,
        row_number() over (
            partition by developer_name
            order by snapshot_date desc
        ) as rn
    from "steam"."main_staging"."stg_games"
    where developer_name is not null
        and developer_name <> ''
)

select
    md5(cast(coalesce(cast(developer_name as TEXT), '_dbt_utils_surrogate_key_null_') as TEXT)) as developer_id,
    developer_name,
    publisher_name
from latest
where rn = 1