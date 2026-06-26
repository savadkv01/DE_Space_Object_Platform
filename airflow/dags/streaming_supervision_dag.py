"""Streaming Supervision DAG.

Runs every 10 minutes to inspect meta.pipeline_run for streaming jobs
that appear stale (no end_time and started > STALE_THRESHOLD_MINUTES ago,
OR ended with status=failed). Writes a summary to the Airflow log so
operators and Prometheus scraping can detect issues.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

STALE_THRESHOLD_MINUTES = 15
STREAMING_PIPELINES = [
    "nasa_neo_stream_producer",
    "celestrak_satcat_stream_producer",
]

default_args = {
    "retries": 0,
}


def check_streaming_health(**context):
    """Query meta.pipeline_run for stale or failed streaming producers."""
    import os
    import psycopg2
    import psycopg2.extras
    from services.common.logging_utils import get_logger

    logger = get_logger(
        "streaming_supervision",
        extra={"component": "streaming_supervisor", "run_id": "-"},
    )

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "space_user"),
        password=os.getenv("POSTGRES_PASSWORD", "space_password"),
        dbname=os.getenv("POSTGRES_DB", "space_warehouse"),
    )
    issues = []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check for failed streaming runs in the last hour
            cur.execute(
                """
                SELECT pipeline_name, run_id, start_time, status, error_message
                FROM meta.pipeline_run
                WHERE pipeline_name = ANY(%s)
                  AND start_time > now() - interval '1 hour'
                  AND status = 'failed'
                ORDER BY start_time DESC
                LIMIT 20;
                """,
                (STREAMING_PIPELINES,),
            )
            failed = cur.fetchall()
            for row in failed:
                msg = (
                    f"FAILED streaming run: pipeline={row['pipeline_name']} "
                    f"run_id={row['run_id']} error={row['error_message']}"
                )
                logger.warning(msg)
                issues.append(msg)

            # Check for runs stuck in 'running' past threshold
            cur.execute(
                """
                SELECT pipeline_name, run_id, start_time
                FROM meta.pipeline_run
                WHERE pipeline_name = ANY(%s)
                  AND status = 'running'
                  AND start_time < now() - interval '%s minutes'
                ORDER BY start_time ASC;
                """,
                (STREAMING_PIPELINES, STALE_THRESHOLD_MINUTES),
            )
            stale = cur.fetchall()
            for row in stale:
                msg = (
                    f"STALE streaming run: pipeline={row['pipeline_name']} "
                    f"run_id={row['run_id']} started={row['start_time']}"
                )
                logger.warning(msg)
                issues.append(msg)
    finally:
        conn.close()

    if issues:
        # Surface issues as a task failure so Airflow alerts
        raise RuntimeError(
            f"Streaming health check found {len(issues)} issue(s):\n"
            + "\n".join(issues)
        )

    logger.info(
        "Streaming health check passed",
        extra={"pipelines_checked": STREAMING_PIPELINES},
    )


with DAG(
    dag_id="streaming_supervision_dag",
    description="Monitors streaming producer health via meta.pipeline_run.",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="*/10 * * * *",
    catchup=False,
    tags=["streaming", "monitoring", "supervision"],
) as dag:
    health_check = PythonOperator(
        task_id="check_streaming_health",
        python_callable=check_streaming_health,
    )
