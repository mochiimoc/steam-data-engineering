
    
    

with child as (
    select tag_id as from_field
    from "steam"."main"."bridge_game_tag"
    where tag_id is not null
),

parent as (
    select tag_id as to_field
    from "steam"."main"."dim_tag"
)

select
    from_field

from child
left join parent
    on child.from_field = parent.to_field

where parent.to_field is null


