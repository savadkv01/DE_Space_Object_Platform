from datetime import date
from typing import Any, Dict, Iterable, List, Mapping

from services.common.db_client import DbClient
from services.ingestion.base_ingestion import BaseBatchIngestionJob
from services.ingestion.nasa_neo.neo_client import NasaNeoClient


class NasaNeoBatchIngestionJob(BaseBatchIngestionJob):
  def __init__(self, start_date: str, end_date: str | None = None):
      super().__init__(pipeline_name="nasa_neo_batch_ingestion")
      self.start_date = start_date
      self.end_date = end_date or start_date
      self.client = NasaNeoClient()
      self.db = DbClient()

  def extract(self) -> Dict[str, Any]:
      self.logger.info(
          "Fetching NASA NEO feed",
          extra={"start_date": self.start_date, "end_date": self.end_date},
      )
      return self.client.fetch_feed(self.start_date, self.end_date)

  def transform(self, raw: Dict[str, Any]) -> Iterable[Mapping[str, Any]]:
      neo_by_date = raw.get("near_earth_objects", {})
      feed_start = self.start_date
      feed_end = self.end_date

      rows: List[Dict[str, Any]] = []

      for approach_date, neos in neo_by_date.items():
          for neo in neos:
              neo_id = neo.get("id")
              neo_ref_id = neo.get("neo_reference_id")
              neo_name = neo.get("name")
              is_hazardous = neo.get("is_potentially_hazardous_asteroid")
              abs_mag = neo.get("absolute_magnitude_h")
              est_diam = neo.get("estimated_diameter")

              for cad in neo.get("close_approach_data", []):
                  row: Dict[str, Any] = {
                      "feed_start_date": feed_start,
                      "feed_end_date": feed_end,
                      "neo_id": neo_id,
                      "neo_reference_id": neo_ref_id,
                      "neo_name": neo_name,
                      "is_potentially_hazardous_asteroid": is_hazardous,
                      "absolute_magnitude_h": abs_mag,
                      "estimated_diameter": est_diam,
                      "close_approach_date": cad.get("close_approach_date"),
                      "close_approach_date_full": cad.get("close_approach_date_full"),
                      "epoch_date_close_approach": cad.get("epoch_date_close_approach"),
                      "relative_velocity": cad.get("relative_velocity"),
                      "miss_distance": cad.get("miss_distance"),
                      "orbiting_body": cad.get("orbiting_body"),
                      "raw_neo": neo,
                  }
                  rows.append(row)

      self.logger.info("Transformed NEO events", extra={"event_count": len(rows)})
      return rows

  def load(self, rows: Iterable[Mapping[str, Any]]) -> int:
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
      count = self.db.executemany(sql, rows)
      return count


def main():
  # Default: ingest today's date; in practice, you may pass explicit dates via env or CLI.
  today = date.today().strftime("%Y-%m-%d")
  job = NasaNeoBatchIngestionJob(start_date=today, end_date=today)
  job.run()


if __name__ == "__main__":
  main()
