with distinct_tags as (
    select distinct tag_name
    from {{ ref('stg_tags') }}
    where tag_name is not null and tag_name <> ''
)

select
    {{ dbt_utils.generate_surrogate_key(['tag_name']) }} as tag_id,
    tag_name
from distinct_tags
