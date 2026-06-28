
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        type as value_field,
        count(*) as n_records

    from "steam"."main"."dim_game"
    group by type

)

select *
from all_values
where value_field not in (
    'game'
)



  
  
      
    ) dbt_internal_test