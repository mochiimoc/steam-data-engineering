with distinct_tags as (
    select distinct tag_name
    from "steam"."main_staging"."stg_tags"
    where tag_name is not null and tag_name <> ''
)

select
    md5(cast(coalesce(cast(tag_name as TEXT), '_dbt_utils_surrogate_key_null_') as TEXT)) as tag_id,
    tag_name
from distinct_tags