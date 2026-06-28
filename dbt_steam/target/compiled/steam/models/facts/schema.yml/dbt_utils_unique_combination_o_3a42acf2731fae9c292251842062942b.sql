





with validation_errors as (

    select
        game_id, date_id
    from "steam"."main"."fact_game_snapshot"
    group by game_id, date_id
    having count(*) > 1

)

select *
from validation_errors


