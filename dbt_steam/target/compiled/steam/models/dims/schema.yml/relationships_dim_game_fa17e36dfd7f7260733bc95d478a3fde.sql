
    
    

with child as (
    select developer_id as from_field
    from "steam"."main"."dim_game"
    where developer_id is not null
),

parent as (
    select developer_id as to_field
    from "steam"."main"."dim_developer"
)

select
    from_field

from child
left join parent
    on child.from_field = parent.to_field

where parent.to_field is null


