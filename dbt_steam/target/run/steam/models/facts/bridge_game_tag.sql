
  
    
    

    create  table
      "steam"."main"."bridge_game_tag__dbt_tmp"
  
    as (
      with latest_votes as (
    select
        game_id,
        tag_name,
        votes,
        row_number() over (
            partition by game_id, tag_name
            order by snapshot_date desc
        ) as rn
    from "steam"."main_staging"."stg_tags"
)

select
    lv.game_id,
    dt.tag_id,
    lv.votes
from latest_votes lv
inner join "steam"."main"."dim_tag" dt
    on lv.tag_name = dt.tag_name
where lv.rn = 1
    );
  
  