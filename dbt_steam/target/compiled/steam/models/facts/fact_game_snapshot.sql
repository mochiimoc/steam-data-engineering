

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
    from "steam"."main_staging"."stg_games" g
    inner join "steam"."main"."dim_game" dg on g.game_id = dg.game_id
    inner join "steam"."main"."dim_date" dd
        on cast(strftime(g.snapshot_date, '%Y%m%d') as integer) = dd.date_id
)

select * from snapshots


where (game_id, date_id) not in (
    select game_id, date_id from "steam"."main"."fact_game_snapshot"
)
