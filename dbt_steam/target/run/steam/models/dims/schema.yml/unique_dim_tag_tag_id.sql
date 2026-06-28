
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

select
    tag_id as unique_field,
    count(*) as n_records

from "steam"."main"."dim_tag"
where tag_id is not null
group by tag_id
having count(*) > 1



  
  
      
    ) dbt_internal_test