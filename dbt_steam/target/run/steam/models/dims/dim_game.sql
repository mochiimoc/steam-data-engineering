
  
    
    

    create  table
      "steam"."main"."dim_game__dbt_tmp"
  
    as (
      with latest as (
    select
        g.game_id,
        g.name,
        g.type,
        g.release_date,
        g.required_age,
        g.is_free,
        g.language_count,
        g.platform_count,
        g.genre,
        g.developer_name,
        g.snapshot_date,
        row_number() over (
            partition by g.game_id
            order by g.snapshot_date desc
        ) as rn
    from "steam"."main_staging"."stg_games" g
),

deduped as (
    select * from latest where rn = 1
)

select
    d.game_id,
    d.name,
    d.type,
    d.release_date,
    d.required_age,
    d.is_free,
    d.language_count,
    d.platform_count,
    d.genre,
    dev.developer_id
from deduped d
left join "steam"."main"."dim_developer" dev
    on d.developer_name = dev.developer_name
    );
  
  