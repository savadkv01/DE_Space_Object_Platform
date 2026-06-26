import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _session_with_retries(
    total: int = 3, backoff_factor: float = 1.5, status_forcelist=(429, 500, 502, 503, 504)
) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class CelesTrakClient:
  def __init__(self, base_url: str | None = None, timeout: int = 20):
      self.base_url = base_url or os.getenv("CELESTRAK_BASE_URL", "https://celestrak.org")
      self.timeout = timeout
      self._session = _session_with_retries()

  def fetch_satcat_csv(self, group: str = "active") -> str:
      url = f"{self.base_url.rstrip('/')}/satcat/records.php"
      resp = self._session.get(
          url, params={"GROUP": group, "FORMAT": "csv"}, timeout=self.timeout
      )
      resp.raise_for_status()
      return resp.text
