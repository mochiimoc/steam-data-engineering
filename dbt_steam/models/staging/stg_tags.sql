with source as (
    select * from read_parquet(
        '{{ env_var("DBT_PROJECT_ROOT", "C:/Users/selcu/Desktop/steamdataengineer") }}/data/silver/game_tags_*.parquet',
        union_by_name=true
    )
)

select
    game_id,
    snapshot_date::date as snapshot_date,
    tag_name,
    coalesce(votes, 0)  as votes
from source
