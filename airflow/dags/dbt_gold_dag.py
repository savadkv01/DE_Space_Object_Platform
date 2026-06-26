"""dbt Gold DAG.

dbt is installed in the Airflow image (see infra/airflow/Dockerfile).
Models run against the postgres warehouse using /dbt/profiles.yml.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

_DBT_CMD = "cd /dbt/space_objects && dbt"
_DBT_FLAGS = "--profiles-dir /dbt --target dev"

default_args = {
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="dbt_gold_dag",
    description="Run dbt silver + gold models against the postgres warehouse.",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["dbt", "silver", "gold"],
) as dag:
    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"{_DBT_CMD} deps {_DBT_FLAGS}",
    )

    dbt_run_silver = BashOperator(
        task_id="dbt_run_silver",
        bash_command=f"{_DBT_CMD} run --select silver.* {_DBT_FLAGS}",
    )

    dbt_run_gold = BashOperator(
        task_id="dbt_run_gold",
        bash_command=f"{_DBT_CMD} run --select gold.* {_DBT_FLAGS}",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{_DBT_CMD} test {_DBT_FLAGS}",
    )

    dbt_deps >> dbt_run_silver >> dbt_run_gold >> dbt_test
