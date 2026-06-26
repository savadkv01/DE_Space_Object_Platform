from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def run_celestrak_satcat_batch(**context):
    """Ingest CelesTrak SATCAT active satellite catalog snapshot into bronze."""
    from services.ingestion.celestrak.celestrak_batch_ingestor import (
        CelesTrakSatcatBatchIngestionJob,
    )

    job = CelesTrakSatcatBatchIngestionJob(
        group="active",
        triggered_by="airflow",
        dag_id=context["dag"].dag_id,
        task_id=context["task"].task_id,
    )
    job.run()


with DAG(
    dag_id="celestrak_batch_dag",
    description="Daily batch ingestion of CelesTrak SATCAT active catalog into bronze.",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["ingestion", "celestrak", "batch"],
) as dag:
    ingest_satcat = PythonOperator(
        task_id="ingest_celestrak_satcat",
        python_callable=run_celestrak_satcat_batch,
    )
