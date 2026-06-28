with source as (
    select * from read_parquet(
        'C:/Users/selcu/Desktop/steamdataengineer/data/silver/games_*.parquet',
        union_by_name=true
    )
)

select
    game_id,
    snapshot_date::date                             as snapshot_date,
    name,
    type,
    release_date::date                              as release_date,
    coalesce(required_age, 0)                       as required_age,
    is_free,
    price,
    initial_price,
    coalesce(discount_pct, 0)                       as discount_pct,
    price_source,
    owners_low,
    owners_high,
    coalesce(positive, 0)                           as positive,
    coalesce(negative, 0)                           as negative,
    positive_ratio,
    coalesce(language_count, 0)                     as language_count,
    coalesce(platform_count, 0)                     as platform_count,
    genre,
    developer_name,
    publisher_name,
    ingested_at::timestamp                          as ingested_at,
    processed_at::timestamp                         as processed_at
from source