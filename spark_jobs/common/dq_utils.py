# spark_jobs/common/dq_utils.py

import json
from typing import Dict, List, Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import LongType, StringType, StructField, StructType


def _write_dq_record(
    spark: SparkSession,
    pg_options: Dict[str, str],
    run_id: str,
    check_name: str,
    status: str,
    total_records: int,
    failed_records: int,
    details: Optional[Dict] = None,
) -> None:
    """
    Internal helper: insert one row into meta.data_quality_run via JDBC.
    meta.data_quality_run schema (from init.sql):

      dq_run_id      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
      run_id         uuid REFERENCES meta.pipeline_run(run_id),
      check_name     text NOT NULL,
      status         text NOT NULL,
      total_records  bigint,
      failed_records bigint,
      details        jsonb,
      created_at     timestamptz NOT NULL DEFAULT now()
    """
    # Serialize details dict to JSON string — JDBC can write a String to jsonb
    details_str = json.dumps(details or {})

    schema = StructType([
        StructField("run_id",         StringType(), True),
        StructField("check_name",     StringType(), True),
        StructField("status",         StringType(), True),
        StructField("total_records",  LongType(),   True),
        StructField("failed_records", LongType(),   True),
        StructField("details",        StringType(), True),
    ])

    dq_df = spark.createDataFrame(
        [(run_id, check_name, status, int(total_records), int(failed_records), details_str)],
        schema=schema,
    )

    (
        dq_df.write
        .format("jdbc")
        .options(**pg_options)
        .option("dbtable", "meta.data_quality_run")
        .mode("append")
        .save()
    )


def dq_check_non_null(
    df: DataFrame,
    column: str,
    check_name: str,
    spark: SparkSession,
    pg_options: Dict[str, str],
    run_id: str,
    fail_on_error: bool = True,
) -> None:
    """
    Check that a column has no NULLs.
    """
    total = df.count()
    failed = df.filter(col(column).isNull()).count()
    status = "pass" if failed == 0 else "fail"

    _write_dq_record(
        spark,
        pg_options,
        run_id,
        check_name,
        status,
        total,
        failed,
        {"column": column},
    )

    if fail_on_error and failed > 0:
        raise ValueError(
            f"DQ check failed: {check_name}, column={column}, failed_records={failed}"
        )


def dq_check_unique(
    df: DataFrame,
    columns: List[str],
    check_name: str,
    spark: SparkSession,
    pg_options: Dict[str, str],
    run_id: str,
    fail_on_error: bool = True,
) -> None:
    """
    Check that a column or combination of columns is unique.
    """
    total = df.count()
    grouped = df.groupBy(*[col(c) for c in columns]).count()
    dup_df = grouped.filter(col("count") > 1)
    failed = dup_df.count()
    status = "pass" if failed == 0 else "fail"

    _write_dq_record(
        spark,
        pg_options,
        run_id,
        check_name,
        status,
        total,
        failed,
        {"columns": columns},
    )

    if fail_on_error and failed > 0:
        raise ValueError(
            f"DQ check failed: {check_name}, columns={columns}, duplicate_groups={failed}"
        )


def dq_check_value_range(
    df: DataFrame,
    column: str,
    check_name: str,
    spark: SparkSession,
    pg_options: Dict[str, str],
    run_id: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    fail_on_error: bool = True,
) -> None:
    """
    Check that values in a numeric column are within [min_value, max_value].
    """
    total = df.count()

    cond = None
    if min_value is not None:
        cond = col(column) < min_value
    if max_value is not None:
        cond = cond | (col(column) > max_value) if cond is not None else (col(column) > max_value)

    if cond is None:
        # Nothing to check
        return

    failed = df.filter(cond).count()
    status = "pass" if failed == 0 else "fail"

    _write_dq_record(
        spark,
        pg_options,
        run_id,
        check_name,
        status,
        total,
        failed,
        {"column": column, "min_value": min_value, "max_value": max_value},
    )

    if fail_on_error and failed > 0:
        raise ValueError(
            f"DQ check failed: {check_name}, column={column}, failed_records={failed}"
        )
