import os
import json
import psycopg2
from psycopg2.extras import execute_batch
from typing import Dict, Any

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json, to_json
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    BooleanType,
    DoubleType,
    LongType,
    MapType,
)


def get_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("neo_stream_to_bronze")
        .master("spark://spark-master:7077")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0"
            ",org.postgresql:postgresql:42.7.3",
        )
        .getOrCreate()
    )


def insert_events_to_bronze(rows: list[Dict[str, Any]]) -> None:
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
            INSERT INTO bronze.nasa_neo_event_raw (
              feed_start_date,
              feed_end_date,
              neo_id,
              neo_reference_id,
              neo_name,
              is_potentially_hazardous_asteroid,
              absolute_magnitude_h,
              estimated_diameter,
              close_approach_date,
              close_approach_date_full,
              epoch_date_close_approach,
              relative_velocity,
              miss_distance,
              orbiting_body,
              raw_neo
            )
            VALUES (
              %(feed_start_date)s,
              %(feed_end_date)s,
              %(neo_id)s,
              %(neo_reference_id)s,
              %(neo_name)s,
              %(is_potentially_hazardous_asteroid)s,
              %(absolute_magnitude_h)s,
              %(estimated_diameter)s,
              %(close_approach_date)s,
              %(close_approach_date_full)s,
              %(epoch_date_close_approach)s,
              %(relative_velocity)s,
              %(miss_distance)s,
              %(orbiting_body)s,
              %(raw_neo)s
            )
            ON CONFLICT (neo_id, close_approach_date_full, orbiting_body) DO NOTHING;
            """
            execute_batch(cur, sql, rows, page_size=1000)
        conn.commit()
    finally:
        conn.close()


def foreach_batch(df: DataFrame, epoch_id: int) -> None:
    if df.rdd.isEmpty():
        return

    schema = StructType([
        StructField("neo_id", StringType()),
        StructField("neo_reference_id", StringType()),
        StructField("neo_name", StringType()),
        StructField("is_potentially_hazardous_asteroid", BooleanType()),
        StructField("absolute_magnitude_h", DoubleType()),
        StructField("estimated_diameter", MapType(StringType(), StringType())),
        StructField("close_approach_date", StringType()),
        StructField("close_approach_date_full", StringType()),
        StructField("epoch_date_close_approach", LongType()),
        StructField("relative_velocity", MapType(StringType(), StringType())),
        StructField("miss_distance", MapType(StringType(), StringType())),
        StructField("orbiting_body", StringType()),
        StructField("raw_neo", MapType(StringType(), StringType())),
    ])

    parsed = df.select(
        from_json(col("value").cast("string"), schema).alias("v")
    )

    # Prepare rows to match bronze.nasa_neo_event_raw
    # feed_start_date/feed_end_date = close_approach_date for streaming
    rows: list[Dict[str, Any]] = []
    for row in parsed.collect():
        v = row["v"]
        if v is None:
            continue

        close_date = v["close_approach_date"]
        rows.append(
            {
                "feed_start_date": close_date,
                "feed_end_date": close_date,
                "neo_id": v["neo_id"],
                "neo_reference_id": v["neo_reference_id"],
                "neo_name": v["neo_name"],
                "is_potentially_hazardous_asteroid": v["is_potentially_hazardous_asteroid"],
                "absolute_magnitude_h": v["absolute_magnitude_h"],
                "estimated_diameter": json.dumps(v["estimated_diameter"]) if v["estimated_diameter"] else None,
                "close_approach_date": v["close_approach_date"],
                "close_approach_date_full": v["close_approach_date_full"],
                "epoch_date_close_approach": v["epoch_date_close_approach"],
                "relative_velocity": json.dumps(v["relative_velocity"]) if v["relative_velocity"] else None,
                "miss_distance": json.dumps(v["miss_distance"]) if v["miss_distance"] else None,
                "orbiting_body": v["orbiting_body"],
                "raw_neo": json.dumps(v["raw_neo"]) if v["raw_neo"] else None,
            }
        )

    insert_events_to_bronze(rows)


def main():
    spark = get_spark()

    df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", os.getenv("KAFKA_BROKER_URL", "kafka:9092"))
        .option("subscribe", "nasa_neo_raw")
        .option("startingOffsets", "earliest")
        .load()
    )

    query = (
        df.writeStream
        .outputMode("update")
        .foreachBatch(foreach_batch)
        .option("checkpointLocation", "/opt/bitnami/spark/checkpoints/neo_stream_to_bronze")
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    main()
