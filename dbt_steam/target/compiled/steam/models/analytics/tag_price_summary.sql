with latest_price as (
    select
        game_id,
        price,
        row_number() over (partition by game_id order by date_id desc) as rn
    from "steam"."main"."fact_game_snapshot"
    where price is not null and price > 0
),

game_price as (
    select game_id, price from latest_price where rn = 1
)

select
    dt.tag_name,
    count(distinct b.game_id)           as game_count,
    round(avg(gp.price), 2)             as avg_price,
    round(median(gp.price), 2)          as median_price,
    round(min(gp.price), 2)             as min_price,
    round(max(gp.price), 2)             as max_price
from "steam"."main"."bridge_game_tag" b
inner join "steam"."main"."dim_tag" dt on b.tag_id = dt.tag_id
inner join game_price gp on b.game_id = gp.game_id
group by dt.tag_name
order by game_count desc