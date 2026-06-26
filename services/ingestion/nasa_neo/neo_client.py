import os
import time
from typing import Any, Dict, Optional

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


class NasaNeoClient:
  BASE_URL = "https://api.nasa.gov"
  # NeoWs allows at most 7 days per request
  MAX_DAYS_PER_REQUEST = 7

  def __init__(self, api_key: Optional[str] = None, timeout: int = 15):
      self.api_key = api_key or os.getenv("NASA_API_KEY")
      if not self.api_key:
          raise RuntimeError("NASA_API_KEY is not set")
      self.timeout = timeout
      self._session = _session_with_retries()

  def _get(self, path: str, **params: Any) -> Dict[str, Any]:
      url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
      params["api_key"] = self.api_key
      resp = self._session.get(url, params=params, timeout=self.timeout)
      resp.raise_for_status()
      return resp.json()

  def fetch_feed(self, start_date: str, end_date: Optional[str] = None) -> Dict[str, Any]:
      params: Dict[str, Any] = {"start_date": start_date}
      if end_date:
          params["end_date"] = end_date
      return self._get("/neo/rest/v1/feed", **params)
