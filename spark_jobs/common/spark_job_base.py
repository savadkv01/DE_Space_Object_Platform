# spark_jobs/common/spark_job_base.py

import os
import uuid
import logging
from datetime import datetime

import psycopg2
from pyspark.sql import SparkSession


class SparkJobBase:
    """
    Base class for all Spark jobs in this project.
    Handles:
      - SparkSession
      - Logging
      - Postgres JDBC read/write
      - Simple pipeline_run logging
    """

    def __init__(self, job_name: str):
        self.job_name = job_name
        self.run_id = str(uuid.uuid4())

        # Create SparkSession
        self.spark = (
            SparkSession.builder
            .appName(job_name)
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )

        # Logging
        self.logger = self._init_logger()

        # JDBC options
        self.pg_options = self._load_pg_options()

    # ----------------- helpers -----------------

    def _init_logger(self):
        logger = logging.getLogger(self.job_name)
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _load_pg_options(self):
        url = os.getenv("POSTGRES_JDBC_URL")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")

        if not url:
            raise ValueError("POSTGRES_JDBC_URL is not set in environment")

        return {
            "url": url,
            "user": user,
            "password": password,
            "driver": "org.postgresql.Driver",
            # Allow Postgres to implicitly cast varchar → uuid
            "stringtype": "unspecified",
        }

    def _pg_conn(self):
        """Return a plain psycopg2 connection using env vars."""
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "space_warehouse"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
        )

    # ----------------- IO helpers -----------------

    def read_table(self, table: str):
        self.logger.info(f"Reading table {table}")
        return (
            self.spark.read
            .format("jdbc")
            .options(**self.pg_options)
            .option("dbtable", table)
            .load()
        )

    def write_table(self, df, table: str, mode: str = "append"):
        self.logger.info(f"Writing to table {table} with mode={mode}")
        (
            df.write
            .format("jdbc")
            .options(**self.pg_options)
            .option("dbtable", table)
            .mode(mode)
            .save()
        )

    # ----------------- template methods -----------------

    def run(self):
        """Override in subclass with main job logic."""
        raise NotImplementedError("Subclasses must implement run()")

    def _insert_pipeline_run_start(self, start_time: datetime) -> None:
        """Insert pipeline_run row with status=running at job start (via psycopg2)."""
        self.logger.info(
            f"Recording pipeline_run start: run_id={self.run_id}"
        )
        sql = """
            INSERT INTO meta.pipeline_run
                (run_id, pipeline_name, start_time, end_time, status)
            VALUES (%s, %s, %s, NULL, 'running')
            ON CONFLICT (run_id) DO NOTHING
        """
        with self._pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (self.run_id, self.job_name, start_time))

    def _update_pipeline_run_end(self, start_time: datetime, status: str) -> None:
        """Update pipeline_run row at job end (via psycopg2)."""
        end_time = datetime.utcnow()
        self.logger.info(
            f"Updating pipeline_run: run_id={self.run_id}, status={status}"
        )
        sql = """
            UPDATE meta.pipeline_run
               SET end_time = %s, status = %s
             WHERE run_id = %s
        """
        with self._pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (end_time, status, self.run_id))

    def execute(self):
        """
        Wrapper that:
          - logs start/end
          - calls run()
          - records meta.pipeline_run
        """
        start_time = datetime.utcnow()
        self.logger.info(f"Starting job {self.job_name}, run_id={self.run_id}")

        # Insert pipeline_run BEFORE running so DQ FK can reference it
        self._insert_pipeline_run_start(start_time)

        status = "success"
        try:
            self.run()
        except Exception as e:
            status = "failed"
            self.logger.exception(f"Job {self.job_name} failed: {e}")
            self._update_pipeline_run_end(start_time, status)
            raise

        self.logger.info(f"Job {self.job_name} finished with status={status}")
        self._update_pipeline_run_end(start_time, status)
