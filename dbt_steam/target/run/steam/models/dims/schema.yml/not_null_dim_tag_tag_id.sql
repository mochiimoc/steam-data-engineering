
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select tag_id
from "steam"."main"."dim_tag"
where tag_id is null



  
  
      
    ) dbt_internal_test