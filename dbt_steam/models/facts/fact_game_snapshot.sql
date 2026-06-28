{{
    config(
        materialized='incremental',
        unique_key=['game_id', 'date_id']
    )
}}

with snapshots as (
    select
        g.game_id,
        cast(strftime(g.snapshot_date, '%Y%m%d') as integer) as date_id,
        g.price,
        g.discount_pct,
        g.initial_price,
        g.owners_low,
        g.owners_high,
        g.positive,
        g.negative
    from {{ ref('stg_games') }} g
    inner join {{ ref('dim_game') }} dg on g.game_id = dg.game_id
    inner join {{ ref('dim_date') }} dd
        on cast(strftime(g.snapshot_date, '%Y%m%d') as integer) = dd.date_id
)

select * from snapshots

{% if is_incremental() %}
where (game_id, date_id) not in (
    select game_id, date_id from {{ this }}
)
{% endif %}
