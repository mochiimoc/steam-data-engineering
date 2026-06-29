
        
            delete from "steam"."main"."fact_game_snapshot" as DBT_INCREMENTAL_TARGET
            using "fact_game_snapshot__dbt_tmp20260628222621219905"
            where (
                
                    "fact_game_snapshot__dbt_tmp20260628222621219905".game_id = DBT_INCREMENTAL_TARGET.game_id
                    and 
                
                    "fact_game_snapshot__dbt_tmp20260628222621219905".date_id = DBT_INCREMENTAL_TARGET.date_id
                    
                
                
            );
        
    

    insert into "steam"."main"."fact_game_snapshot" ("game_id", "date_id", "price", "discount_pct", "initial_price", "owners_low", "owners_high", "positive", "negative")
    (
        select "game_id", "date_id", "price", "discount_pct", "initial_price", "owners_low", "owners_high", "positive", "negative"
        from "fact_game_snapshot__dbt_tmp20260628222621219905"
    )
  