import csv
from datetime import date
from io import StringIO
from typing import Any, Dict, Iterable, List, Mapping, Optional

from services.common.db_client import DbClient
from services.ingestion.base_ingestion import BaseBatchIngestionJob
from services.ingestion.celestrak.celestrak_client import CelesTrakClient


class CelesTrakSatcatBatchIngestionJob(BaseBatchIngestionJob):
  def __init__(
      self,
      group: str = "active",
      triggered_by: str = "manual",
      dag_id: Optional[str] = None,
      task_id: Optional[str] = None,
  ):
      super().__init__(
          pipeline_name="celestrak_satcat_batch_ingestion",
          triggered_by=triggered_by,
          dag_id=dag_id,
          task_id=task_id,
      )
      self.group = group
      self.client = CelesTrakClient()
      self.db = DbClient()

  def extract(self) -> str:
      self.logger.info("Fetching CelesTrak SATCAT CSV", extra={"group": self.group})
      return self.client.fetch_satcat_csv(self.group)

  def transform(self, raw_csv: str) -> Iterable[Mapping[str, Any]]:
      snapshot_date = date.today().isoformat()
      rows: List[Dict[str, Any]] = []

      f = StringIO(raw_csv)
      reader = csv.DictReader(f)
      for line in reader:
          rows.append(
              {
                  "snapshot_group": self.group,
                  "snapshot_date": snapshot_date,
                  "raw_csv_row": ",".join([line.get(field, "") for field in reader.fieldnames]),
                  "parsed_record": line,
              }
          )

      self.logger.info("Transformed SATCAT records", extra={"record_count": len(rows)})
      return rows

  def load(self, rows: Iterable[Mapping[str, Any]]) -> int:
      snapshot_date = date.today().isoformat()

      # Idempotent: skip if a snapshot for this group+date already exists
      existing = self.db.execute(
          """
          SELECT COUNT(*) AS cnt FROM bronze.celestrak_satcat_raw
          WHERE snapshot_group = %(group)s AND snapshot_date = %(date)s
          """,
          {"group": self.group, "date": snapshot_date},
          fetchone=True,
      )
      if existing and (existing.get("cnt") or 0) > 0:
          self.logger.info(
              "SATCAT snapshot already ingested, skipping",
              extra={"snapshot_group": self.group, "snapshot_date": snapshot_date},
          )
          return 0

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
      count = self.db.executemany(sql, rows)
      return count


def main():
  job = CelesTrakSatcatBatchIngestionJob(group="active")
  job.run()


if __name__ == "__main__":
  main()
