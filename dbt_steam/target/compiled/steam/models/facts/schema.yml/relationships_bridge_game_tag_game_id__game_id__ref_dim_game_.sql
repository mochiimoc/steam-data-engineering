
    
    

with child as (
    select game_id as from_field
    from "steam"."main"."bridge_game_tag"
    where game_id is not null
),

parent as (
    select game_id as to_field
    from "steam"."main"."dim_game"
)

select
    from_field

from child
left join parent
    on child.from_field = parent.to_field

where parent.to_field is null


