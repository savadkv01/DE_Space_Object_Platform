from pyspark.sql.functions import col, lit, min as spark_min, max as spark_max, get_json_object

from common.spark_job_base import SparkJobBase
from common.dq_utils import (
    dq_check_non_null,
    dq_check_unique,
    dq_check_value_range,
)


class BronzeToSilverNEOJob(SparkJobBase):
    def __init__(self):
        # This pipeline_name is used in meta.pipeline_run and by Airflow DQ gate
        super().__init__("bronze_to_silver_neo")

    def run(self):
        # 1) Read Bronze
        bronze_df = self.read_table("bronze.nasa_neo_event_raw")
        self.logger.info(f"Bronze NEO events count = {bronze_df.count()}")

        if bronze_df.rdd.isEmpty():
            self.logger.info("No NEO events in bronze; nothing to do.")
            return

        # 2) Build NEO dimension from Bronze
        neo_dim_df = (
            bronze_df
            .groupBy(
                "neo_id",
                "neo_reference_id",
                col("neo_name").alias("name"),
                "absolute_magnitude_h",
                "is_potentially_hazardous_asteroid",
                "estimated_diameter",
            )
            .agg(
                spark_min("close_approach_date").alias("first_seen_date"),
                spark_max("close_approach_date").alias("last_seen_date"),
            )
            .select(
                col("neo_id"),
                col("neo_reference_id"),
                col("name"),
                col("absolute_magnitude_h"),
                # Parse diameter from the stored JSONB field (km min/max)
                get_json_object(
                    col("estimated_diameter").cast("string"),
                    "$.kilometers.estimated_diameter_min",
                ).cast("double").alias("estimated_diameter_km_min"),
                get_json_object(
                    col("estimated_diameter").cast("string"),
                    "$.kilometers.estimated_diameter_max",
                ).cast("double").alias("estimated_diameter_km_max"),
                col("is_potentially_hazardous_asteroid"),
                lit(None).cast("boolean").alias("is_sentry_object"),
                lit(None).cast("string").alias("nasa_jpl_url"),
                col("first_seen_date"),
                col("last_seen_date"),
            )
        )

        self.logger.info(
            f"Silver NEO dim rows computed (before merge) = {neo_dim_df.count()}"
        )

        # 3) Idempotent insert: keep only new neo_id values
        try:
            existing_neo_df = (
                self.read_table("silver.neo")
                .select("neo_id")
                .distinct()
            )
            self.logger.info(
                f"Existing NEO dim rows in silver.neo = {existing_neo_df.count()}"
            )

            neo_new_df = neo_dim_df.join(
                existing_neo_df, on="neo_id", how="left_anti"
            )
            self.logger.info(
                f"New NEO dim rows to insert = {neo_new_df.count()}"
            )
        except Exception as e:
            # First run / table missing: treat as no existing data
            self.logger.info(
                f"Could not read silver.neo (maybe first run): {e}"
            )
            neo_new_df = neo_dim_df
            self.logger.info(
                f"Inserting all NEO dim rows = {neo_new_df.count()}"
            )

        if neo_new_df.rdd.isEmpty():
            self.logger.info("No new NEOs to insert into silver.neo")
            return

        # 4) DQ checks before write (results go to meta.data_quality_run)
        dq_check_non_null(
            neo_new_df,
            column="neo_id",
            check_name="silver.neo.non_null_neo_id",
            spark=self.spark,
            pg_options=self.pg_options,
            run_id=self.run_id,
        )

        dq_check_unique(
            neo_new_df,
            columns=["neo_id"],
            check_name="silver.neo.unique_neo_id",
            spark=self.spark,
            pg_options=self.pg_options,
            run_id=self.run_id,
        )

        dq_check_value_range(
            neo_new_df,
            column="absolute_magnitude_h",
            check_name="silver.neo.abs_mag_reasonable_range",
            spark=self.spark,
            pg_options=self.pg_options,
            run_id=self.run_id,
            min_value=-5.0,
            max_value=40.0,
        )

        # 5) Write to Silver
        self.write_table(neo_new_df, "silver.neo")

        # ------------------------------------------------------------------
        # 6) Build close-approach fact table (silver.neo_close_approach)
        # ------------------------------------------------------------------
        self.logger.info("Building silver.neo_close_approach fact table")

        # Re-read silver.neo to get neo_sk surrogate keys
        neo_silver_df = (
            self.read_table("silver.neo")
            .select("neo_sk", "neo_id")
            .distinct()
        )

        close_approach_df = (
            bronze_df
            .select(
                col("neo_id"),
                col("close_approach_date"),
                col("close_approach_date_full"),
                col("epoch_date_close_approach"),
                col("orbiting_body"),
                get_json_object(col("relative_velocity").cast("string"),
                    "$.kilometers_per_second").cast("double").alias("rel_velocity_km_s"),
                get_json_object(col("relative_velocity").cast("string"),
                    "$.kilometers_per_hour").cast("double").alias("rel_velocity_km_h"),
                get_json_object(col("relative_velocity").cast("string"),
                    "$.miles_per_hour").cast("double").alias("rel_velocity_mi_h"),
                get_json_object(col("miss_distance").cast("string"),
                    "$.kilometers").cast("double").alias("miss_distance_km"),
                get_json_object(col("miss_distance").cast("string"),
                    "$.lunar").cast("double").alias("miss_distance_lunar"),
                get_json_object(col("miss_distance").cast("string"),
                    "$.astronomical").cast("double").alias("miss_distance_au"),
                get_json_object(col("miss_distance").cast("string"),
                    "$.miles").cast("double").alias("miss_distance_miles"),
            )
            .join(neo_silver_df, on="neo_id", how="inner")
            .dropDuplicates(["neo_id", "close_approach_date_full", "orbiting_body"])
        )

        self.logger.info(
            f"Close-approach rows (before merge) = {close_approach_df.count()}"
        )

        # Idempotent: skip already-loaded close approaches
        try:
            existing_ca_df = (
                self.read_table("silver.neo_close_approach")
                .select("neo_id", "close_approach_date_full", "orbiting_body")
                .distinct()
            )
            ca_new_df = close_approach_df.join(
                existing_ca_df,
                on=["neo_id", "close_approach_date_full", "orbiting_body"],
                how="left_anti",
            )
        except Exception as e:
            self.logger.info(f"Could not read silver.neo_close_approach (first run?): {e}")
            ca_new_df = close_approach_df

        self.logger.info(
            f"New close-approach rows to insert = {ca_new_df.count()}"
        )

        if ca_new_df.rdd.isEmpty():
            self.logger.info("No new close-approach rows to insert")
            return

        dq_check_non_null(
            ca_new_df, column="neo_id",
            check_name="silver.neo_close_approach.non_null_neo_id",
            spark=self.spark, pg_options=self.pg_options, run_id=self.run_id,
        )
        dq_check_non_null(
            ca_new_df, column="close_approach_date",
            check_name="silver.neo_close_approach.non_null_date",
            spark=self.spark, pg_options=self.pg_options, run_id=self.run_id,
        )

        self.write_table(ca_new_df, "silver.neo_close_approach")


if __name__ == "__main__":
    job = BronzeToSilverNEOJob()
    job.execute()
