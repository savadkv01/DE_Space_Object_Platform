import os
import requests


class CelesTrakClient:
  def __init__(self, base_url: str | None = None, timeout: int = 20):
      self.base_url = base_url or os.getenv("CELESTRAK_BASE_URL", "https://celestrak.org")
      self.timeout = timeout

  def fetch_satcat_csv(self, group: str = "active") -> str:
      url = f"{self.base_url.rstrip('/')}/satcat/records.php"
      resp = requests.get(url, params={"GROUP": group, "FORMAT": "csv"}, timeout=self.timeout)
      resp.raise_for_status()
      return resp.text
