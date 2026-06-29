from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.models import Variable

PROJECT = "/opt/airflow/project"
DBT_DIR = f"{PROJECT}/dbt_steam"

# Airflow UI'dan Variables → extract_limit ile kaç oyun çekileceği ayarlanır.
# Varsayılan 50 → demo için hız, production için 10000.
EXTRACT_LIMIT = int(Variable.get("extract_limit", default_var="50"))

with DAG(
    dag_id="steam_pipeline",
    description="Extract → Silver → dbt run → dbt test",
    schedule=None,           # manuel tetik; günlük otomatik çalışma YOK
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["steam", "portfolio"],
) as dag:

    extract = BashOperator(
        task_id="extract",
        bash_command=(
            f"cd {PROJECT} && "
            f"python -m ingestion.harvest --limit {EXTRACT_LIMIT} --date {{{{ ds }}}}"
        ),
    )

    silver = BashOperator(
        task_id="silver",
        bash_command=(
            f"cd {PROJECT} && "
            "python transform/transform.py {{ ds }}"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"cd {DBT_DIR} && "
            "dbt run --profiles-dir . --no-partial-parse"
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {DBT_DIR} && "
            "dbt test --profiles-dir . --no-partial-parse"
        ),
    )

    extract >> silver >> dbt_run >> dbt_test
