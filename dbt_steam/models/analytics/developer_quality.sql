with latest_snapshot as (
    select
        f.game_id,
        f.positive,
        f.negative,
        case
            when (f.positive + f.negative) > 0
            then round(f.positive * 1.0 / (f.positive + f.negative), 4)
            else null
        end as positive_ratio,
        row_number() over (partition by f.game_id order by f.date_id desc) as rn
    from {{ ref('fact_game_snapshot') }} f
),

game_quality as (
    select game_id, positive_ratio
    from latest_snapshot
    where rn = 1 and positive_ratio is not null
)

select
    dev.developer_id,
    dev.developer_name,
    count(distinct g.game_id)               as game_count,
    round(avg(gq.positive_ratio), 4)        as avg_positive_ratio,
    round(min(gq.positive_ratio), 4)        as min_positive_ratio,
    round(max(gq.positive_ratio), 4)        as max_positive_ratio
from {{ ref('dim_developer') }} dev
inner join {{ ref('dim_game') }} g on dev.developer_id = g.developer_id
inner join game_quality gq on g.game_id = gq.game_id
group by dev.developer_id, dev.developer_name
order by avg_positive_ratio desc, game_count desc
