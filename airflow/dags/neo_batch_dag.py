from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def run_neo_batch(**context):
    """Ingest NASA NEO close-approach events for the Airflow execution date."""
    from services.ingestion.nasa_neo.neo_batch_ingestor import NasaNeoBatchIngestionJob

    execution_date = context["ds"]  # YYYY-MM-DD string
    job = NasaNeoBatchIngestionJob(
        start_date=execution_date,
        end_date=execution_date,
        triggered_by="airflow",
        dag_id=context["dag"].dag_id,
        task_id=context["task"].task_id,
    )
    job.run()


with DAG(
    dag_id="neo_batch_dag",
    description="Daily batch ingestion of NASA NEO close-approach events into bronze.",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["ingestion", "neo", "batch"],
) as dag:
    ingest_neo = PythonOperator(
        task_id="ingest_neo_batch",
        python_callable=run_neo_batch,
    )
