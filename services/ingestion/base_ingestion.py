from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping, Optional

from services.common.db_client import DbClient
from services.common.logging_utils import get_logger


class BaseBatchIngestionJob(ABC):
  """
  Template for batch ingestion:
  - create pipeline_run
  - extract -> transform -> load
  - update pipeline_run on success/failure
  """

  def __init__(
      self,
      pipeline_name: str,
      triggered_by: str = "manual",
      dag_id: Optional[str] = None,
      task_id: Optional[str] = None,
  ) -> None:
      self.pipeline_name = pipeline_name
      self.triggered_by = triggered_by
      self.dag_id = dag_id
      self.task_id = task_id
      self.db = DbClient()
      # run_id created later
      self.run_id: Optional[str] = None
      self.logger = get_logger(
          self.__class__.__name__,
          extra={"component": pipeline_name, "run_id": "-"},
      )

  def run(self) -> None:
      self.run_id = self.db.create_pipeline_run(
          pipeline_name=self.pipeline_name,
          triggered_by=self.triggered_by,
          dag_id=self.dag_id,
          task_id=self.task_id,
      )
      # update logger with run_id
      self.logger = get_logger(
          self.__class__.__name__,
          extra={"component": self.pipeline_name, "run_id": self.run_id},
      )
      self.logger.info("Starting batch ingestion")

      try:
          raw = self.extract()
          rows = self.transform(raw)
          count = self.load(rows)
          self.db.update_pipeline_run(self.run_id, "success", records_processed=count)
          self.logger.info("Batch ingestion completed", extra={"records_processed": count})
      except Exception as exc:
          self.logger.exception("Batch ingestion failed")
          if self.run_id:
              self.db.update_pipeline_run(
                  self.run_id,
                  "failed",
                  error_message=str(exc),
              )
          raise

  @abstractmethod
  def extract(self) -> Any:
      ...

  @abstractmethod
  def transform(self, raw: Any) -> Iterable[Mapping[str, Any]]:
      ...

  @abstractmethod
  def load(self, rows: Iterable[Mapping[str, Any]]) -> int:
      ...
