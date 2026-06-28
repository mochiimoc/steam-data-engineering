
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select developer_id
from "steam"."main"."dim_developer"
where developer_id is null



  
  
      
    ) dbt_internal_test