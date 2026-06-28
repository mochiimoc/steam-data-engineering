with latest_snapshot as (
    select
        f.game_id,
        f.owners_high,
        f.positive,
        f.negative,
        case
            when (f.positive + f.negative) > 0
            then round(f.positive * 1.0 / (f.positive + f.negative), 4)
            else null
        end as positive_ratio,
        row_number() over (partition by f.game_id order by f.date_id desc) as rn
    from {{ ref('fact_game_snapshot') }} f
)

select
    g.game_id,
    g.name,
    g.genre,
    g.release_date,
    s.owners_high,
    s.positive_ratio,
    s.positive,
    s.negative
from latest_snapshot s
inner join {{ ref('dim_game') }} g on s.game_id = g.game_id
where s.rn = 1
    and s.positive_ratio >= 0.85
    and s.owners_high <= 500000
    and (s.positive + s.negative) >= 10
order by s.positive_ratio desc, s.owners_high desc
