import os
import json
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime
from typing import Dict, Any, List

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    MapType,
)


def get_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("celestrak_stream_to_bronze")
        .master("spark://spark-master:7077")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0"
            ",org.postgresql:postgresql:42.7.3",
        )
        .getOrCreate()
    )


def insert_satcat_to_bronze(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "space_user"),
        password=os.getenv("POSTGRES_PASSWORD", "space_password"),
        dbname=os.getenv("POSTGRES_DB", "space_warehouse"),
    )
    try:
        with conn.cursor() as cur:
            sql = """
            INSERT INTO bronze.celestrak_satcat_raw (
                snapshot_group,
                snapshot_date,
                raw_csv_row,
                parsed_record
            )
            VALUES (
                %(snapshot_group)s,
                %(snapshot_date)s,
                %(raw_csv_row)s,
                %(parsed_record)s
            );
            """
            execute_batch(cur, sql, rows, page_size=1000)
        conn.commit()
    finally:
        conn.close()


def foreach_batch(df: DataFrame, epoch_id: int) -> None:
    if df.rdd.isEmpty():
        return

    schema = StructType([
        StructField("snapshot_group", StringType()),
        StructField("snapshot_timestamp", StringType()),
        StructField("satcat", MapType(StringType(), StringType())),
    ])

    parsed = df.select(
        from_json(col("value").cast("string"), schema).alias("v")
    )

    rows: List[Dict[str, Any]] = []

    for row in parsed.collect():
        v = row["v"]
        if v is None:
            continue

        group = v["snapshot_group"]
        ts = v["snapshot_timestamp"]
        satcat = v["satcat"] or {}

        # Derive snapshot_date from timestamp (UTC date)
        try:
            dt = datetime.fromisoformat(ts)
            snapshot_date = dt.date().isoformat()
        except Exception:
            snapshot_date = ts[:10]  # fallback YYYY-MM-DD

        rows.append(
            {
                "snapshot_group": group,
                "snapshot_date": snapshot_date,
                # For streaming we just store the SATCAT record as JSON text in raw_csv_row
                "raw_csv_row": json.dumps(satcat),
                "parsed_record": json.dumps(satcat),
            }
        )

    insert_satcat_to_bronze(rows)


def main():
    spark = get_spark()

    df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", os.getenv("KAFKA_BROKER_URL", "kafka:9092"))
        .option("subscribe", "celestrak_satcat_raw")
        .option("startingOffsets", "earliest")
        .load()
    )

    query = (
        df.writeStream
        .outputMode("update")
        .foreachBatch(foreach_batch)
        .option("checkpointLocation", "/opt/bitnami/spark/checkpoints/celestrak_stream_to_bronze")
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    main()
