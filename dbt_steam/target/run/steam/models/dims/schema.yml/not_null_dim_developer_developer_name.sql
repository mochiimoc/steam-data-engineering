
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select developer_name
from "steam"."main"."dim_developer"
where developer_name is null



  
  
      
    ) dbt_internal_test