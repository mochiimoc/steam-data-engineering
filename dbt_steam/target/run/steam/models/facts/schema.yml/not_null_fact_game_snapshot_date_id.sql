
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select date_id
from "steam"."main"."fact_game_snapshot"
where date_id is null



  
  
      
    ) dbt_internal_test