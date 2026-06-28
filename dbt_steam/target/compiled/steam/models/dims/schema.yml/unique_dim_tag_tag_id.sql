
    
    

select
    tag_id as unique_field,
    count(*) as n_records

from "steam"."main"."dim_tag"
where tag_id is not null
group by tag_id
having count(*) > 1


