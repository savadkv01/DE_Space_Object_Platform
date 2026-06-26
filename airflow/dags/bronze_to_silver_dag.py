"""Bronze → Silver Spark transformation DAG.

Submits both Spark jobs (NEO + CelesTrak) sequentially to spark-master.
Spark client is available at SPARK_HOME=/opt/spark inside the Airflow container.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

_SPARK_SUBMIT = (
    "PYTHONPATH=/opt/airflow/spark_jobs:$PYTHONPATH "
    "spark-submit "
    "--master spark://spark-master:7077 "
    "--conf spark.driver.host=airflow-scheduler "
    "--conf spark.driver.bindAddress=0.0.0.0 "
    "--conf spark.sql.session.timeZone=UTC "
)

default_args = {
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="bronze_to_silver_dag",
    description="Spark jobs promoting bronze NEO and CelesTrak data to silver.",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["spark", "bronze", "silver"],
) as dag:
    neo_bronze_to_silver = BashOperator(
        task_id="neo_bronze_to_silver",
        bash_command=(
            f"{_SPARK_SUBMIT} /opt/airflow/spark_jobs/bronze_to_silver_neo.py"
        ),
    )

    celestrak_bronze_to_silver = BashOperator(
        task_id="celestrak_bronze_to_silver",
        bash_command=(
            f"{_SPARK_SUBMIT} /opt/airflow/spark_jobs/bronze_to_silver_celestrak.py"
        ),
    )

    # Run sequentially to avoid concurrent JDBC writes to shared tables
    neo_bronze_to_silver >> celestrak_bronze_to_silver
