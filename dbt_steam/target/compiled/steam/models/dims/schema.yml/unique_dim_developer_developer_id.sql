
    
    

select
    developer_id as unique_field,
    count(*) as n_records

from "steam"."main"."dim_developer"
where developer_id is not null
group by developer_id
having count(*) > 1


