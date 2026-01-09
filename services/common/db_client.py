import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json



@dataclass
class PostgresConfig:
  host: str
  port: int
  user: str
  password: str
  db: str


def load_pg_config() -> PostgresConfig:
  return PostgresConfig(
      host=os.getenv("POSTGRES_HOST", "postgres"),
      port=int(os.getenv("POSTGRES_PORT", "5432")),
      user=os.getenv("POSTGRES_USER", "space_user"),
      password=os.getenv("POSTGRES_PASSWORD", "space_password"),
      db=os.getenv("POSTGRES_DB", "space_warehouse"),
  )


class DbClient:
  def __init__(self, config: Optional[PostgresConfig] = None):
      self._config = config or load_pg_config()

  @contextmanager
  def get_conn(self):
      conn = psycopg2.connect(
          host=self._config.host,
          port=self._config.port,
          user=self._config.user,
          password=self._config.password,
          dbname=self._config.db,
      )
      try:
          yield conn
      finally:
          conn.close()

  def execute(
      self,
      sql: str,
      params: Optional[Mapping[str, Any]] = None,
      fetchone: bool = False,
  ) -> Optional[Mapping[str, Any]]:
      with self.get_conn() as conn:
          with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
              cur.execute(sql, params or {})
              result = cur.fetchone() if fetchone else None
              conn.commit()
              return result

  def executemany(
      self,
      sql: str,
      rows: Iterable[Mapping[str, Any]],
  ) -> int:
      rows_list = list(rows)
      if not rows_list:
          return 0

      # Adapt dict/list values to JSON for psycopg2
      adapted_rows = []
      for row in rows_list:
          adapted = {}
          for k, v in row.items():
              if isinstance(v, (dict, list)):
                  adapted[k] = Json(v)
              else:
                  adapted[k] = v
          adapted_rows.append(adapted)

      with self.get_conn() as conn:
          with conn.cursor() as cur:
              psycopg2.extras.execute_batch(cur, sql, adapted_rows, page_size=1000)
              conn.commit()
              # Return number of rows we attempted to load
              return len(rows_list)


  def create_pipeline_run(
      self,
      pipeline_name: str,
      triggered_by: str = "manual",
      dag_id: Optional[str] = None,
      task_id: Optional[str] = None,
  ) -> str:
      sql = """
      INSERT INTO meta.pipeline_run (pipeline_name, triggered_by, dag_id, task_id, status)
      VALUES (%(pipeline_name)s, %(triggered_by)s, %(dag_id)s, %(task_id)s, 'running')
      RETURNING run_id;
      """
      row = self.execute(
          sql,
          {
              "pipeline_name": pipeline_name,
              "triggered_by": triggered_by,
              "dag_id": dag_id,
              "task_id": task_id,
          },
          fetchone=True,
      )
      return str(row["run_id"])

  def update_pipeline_run(
      self,
      run_id: str,
      status: str,
      records_processed: Optional[int] = None,
      error_message: Optional[str] = None,
  ) -> None:
      sql = """
      UPDATE meta.pipeline_run
      SET status = %(status)s,
          end_time = now(),
          records_processed = COALESCE(%(records_processed)s, records_processed),
          error_message = COALESCE(%(error_message)s, error_message)
      WHERE run_id = %(run_id)s;
      """
      self.execute(
          sql,
          {
              "run_id": run_id,
              "status": status,
              "records_processed": records_processed,
              "error_message": error_message,
          },
      )
