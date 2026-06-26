from pyspark.sql.functions import (
    col,
    get_json_object,
    min as spark_min,
    max as spark_max,
    lit,
    to_date,
    when,
)

from common.spark_job_base import SparkJobBase
from common.dq_utils import (
    dq_check_non_null,
    dq_check_unique,
    dq_check_value_range,
)


class BronzeToSilverCelestrakJob(SparkJobBase):
    """
    Bronze -> Silver for CelesTrak SATCAT data.

    Reads bronze.celestrak_satcat_raw (parsed_record JSONB) and builds:
      * silver.satcat_satellite      (dimension, one row per norad_cat_id)
      * silver.satcat_orbit_snapshot (fact, one row per norad_cat_id + snapshot_date)

    Idempotent:
      * Satellite dim:     only inserts new norad_cat_id values
      * Orbit snapshot:    only inserts new (norad_cat_id, snapshot_date) combinations
    """

    def __init__(self):
        super().__init__("bronze_to_silver_celestrak")

    def run(self):
        # ------------------------------------------------------------------
        # 1) Read Bronze SATCAT data and extract fields from parsed_record JSON
        # ------------------------------------------------------------------
        satcat_df = self.read_table("bronze.celestrak_satcat_raw")
        total = satcat_df.count()
        self.logger.info(f"Bronze CelesTrak SATCAT rows = {total}")

        if satcat_df.rdd.isEmpty():
            self.logger.info("No SATCAT data in bronze; nothing to do.")
            return

        pr = col("parsed_record").cast("string")

        parsed_df = satcat_df.select(
            col("snapshot_date"),
            col("snapshot_group").alias("source_group"),
            get_json_object(pr, "$.NORAD_CAT_ID").cast("int").alias("norad_cat_id"),
            get_json_object(pr, "$.OBJECT_ID").alias("object_id"),
            get_json_object(pr, "$.OBJECT_NAME").alias("object_name"),
            get_json_object(pr, "$.OBJECT_TYPE").alias("object_type"),
            get_json_object(pr, "$.OWNER").alias("owner"),
            get_json_object(pr, "$.OPS_STATUS_CODE").alias("ops_status_code"),
            when(
                get_json_object(pr, "$.LAUNCH_DATE") == "", lit(None)
            ).otherwise(
                to_date(get_json_object(pr, "$.LAUNCH_DATE"), "yyyy-MM-dd")
            ).alias("launch_date"),
            get_json_object(pr, "$.LAUNCH_SITE").alias("launch_site"),
            when(
                get_json_object(pr, "$.DECAY_DATE") == "", lit(None)
            ).otherwise(
                to_date(get_json_object(pr, "$.DECAY_DATE"), "yyyy-MM-dd")
            ).alias("decay_date"),
            get_json_object(pr, "$.ORBIT_CENTER").alias("orbit_center"),
            get_json_object(pr, "$.ORBIT_TYPE").alias("orbit_type"),
            get_json_object(pr, "$.RCS").cast("double").alias("rcs"),
            get_json_object(pr, "$.PERIOD").cast("double").alias("period_minutes"),
            get_json_object(pr, "$.INCLINATION").cast("double").alias("inclination_deg"),
            get_json_object(pr, "$.APOGEE").cast("double").alias("apogee_km"),
            get_json_object(pr, "$.PERIGEE").cast("double").alias("perigee_km"),
        ).filter(col("norad_cat_id").isNotNull())

        # ------------------------------------------------------------------
        # 2) Build SATCAT satellite dimension
        # ------------------------------------------------------------------
        sat_dim_df = (
            parsed_df
            .groupBy(
                "norad_cat_id", "object_id", "object_name", "object_type",
                "owner", "ops_status_code", "launch_date", "launch_site",
                "decay_date", "orbit_center", "orbit_type", "rcs",
            )
            .agg(
                spark_min("snapshot_date").alias("first_seen_date"),
                spark_max("snapshot_date").alias("last_seen_date"),
            )
            .dropDuplicates(["norad_cat_id"])
        )

        self.logger.info(
            f"SATCAT dim rows computed (before merge) = {sat_dim_df.count()}"
        )

        # Idempotent insert: only new norad_cat_id values
        try:
            existing_sat_df = (
                self.read_table("silver.satcat_satellite")
                .select("norad_cat_id")
                .distinct()
            )
            self.logger.info(
                f"Existing satellites in silver.satcat_satellite = {existing_sat_df.count()}"
            )
            sat_new_df = sat_dim_df.join(
                existing_sat_df, on="norad_cat_id", how="left_anti"
            )
            self.logger.info(
                f"New satellites to insert = {sat_new_df.count()}"
            )
        except Exception as e:
            self.logger.info(
                f"Could not read silver.satcat_satellite (maybe first run): {e}"
            )
            sat_new_df = sat_dim_df

        if not sat_new_df.rdd.isEmpty():
            dq_check_non_null(
                sat_new_df,
                column="norad_cat_id",
                check_name="silver.satcat_satellite.non_null_norad_cat_id",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
            )
            dq_check_unique(
                sat_new_df,
                columns=["norad_cat_id"],
                check_name="silver.satcat_satellite.unique_norad_cat_id",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
            )
            dq_check_non_null(
                sat_new_df,
                column="object_name",
                check_name="silver.satcat_satellite.non_null_object_name",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
            )
            self.write_table(sat_new_df, "silver.satcat_satellite")
        else:
            self.logger.info("No new satellites to insert into silver.satcat_satellite")

        # ------------------------------------------------------------------
        # 3) Build orbit snapshot fact table
        # ------------------------------------------------------------------
        sat_silver_df = (
            self.read_table("silver.satcat_satellite")
            .select("satellite_sk", "norad_cat_id")
            .distinct()
        )
        self.logger.info(
            f"Loaded {sat_silver_df.count()} satellite_sk mappings"
        )

        orbit_candidate_df = (
            parsed_df
            .select(
                col("norad_cat_id"),
                col("snapshot_date"),
                col("source_group"),
                col("period_minutes"),
                col("inclination_deg"),
                col("apogee_km"),
                col("perigee_km"),
            )
            .dropDuplicates(["norad_cat_id", "snapshot_date", "source_group"])
        )

        self.logger.info(
            f"Orbit snapshot candidates = {orbit_candidate_df.count()}"
        )

        orbit_with_sk_df = (
            orbit_candidate_df
            .join(sat_silver_df, on="norad_cat_id", how="inner")
            .select(
                col("satellite_sk"),
                col("norad_cat_id"),
                col("snapshot_date"),
                col("period_minutes"),
                col("inclination_deg"),
                col("apogee_km"),
                col("perigee_km"),
                lit(None).cast("double").alias("ecc"),
                lit(None).cast("double").alias("mean_motion_rev_per_day"),
                col("source_group"),
            )
        )

        # Idempotent insert
        try:
            existing_orbit_df = (
                self.read_table("silver.satcat_orbit_snapshot")
                .select("norad_cat_id", "snapshot_date")
                .distinct()
            )
            self.logger.info(
                f"Existing orbit snapshots = {existing_orbit_df.count()}"
            )
            orbit_new_df = orbit_with_sk_df.join(
                existing_orbit_df,
                on=["norad_cat_id", "snapshot_date"],
                how="left_anti",
            )
            self.logger.info(
                f"New orbit snapshots to insert = {orbit_new_df.count()}"
            )
        except Exception as e:
            self.logger.info(
                f"Could not read silver.satcat_orbit_snapshot (maybe first run): {e}"
            )
            orbit_new_df = orbit_with_sk_df

        if not orbit_new_df.rdd.isEmpty():
            dq_check_non_null(
                orbit_new_df,
                column="norad_cat_id",
                check_name="silver.satcat_orbit_snapshot.non_null_norad_cat_id",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
            )
            dq_check_non_null(
                orbit_new_df,
                column="snapshot_date",
                check_name="silver.satcat_orbit_snapshot.non_null_snapshot_date",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
            )
            dq_check_unique(
                orbit_new_df,
                columns=["norad_cat_id", "snapshot_date"],
                check_name="silver.satcat_orbit_snapshot.unique_norad_snapshot_date",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
            )
            dq_check_value_range(
                orbit_new_df,
                column="apogee_km",
                check_name="silver.satcat_orbit_snapshot.apogee_non_negative",
                spark=self.spark,
                pg_options=self.pg_options,
                run_id=self.run_id,
                min_value=0.0,
            )
            self.write_table(orbit_new_df, "silver.satcat_orbit_snapshot")
        else:
            self.logger.info(
                "No new orbit snapshots to insert into silver.satcat_orbit_snapshot"
            )


if __name__ == "__main__":
    job = BronzeToSilverCelestrakJob()
    job.execute()
