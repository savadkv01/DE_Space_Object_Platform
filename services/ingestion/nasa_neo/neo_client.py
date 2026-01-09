import os
from typing import Any, Dict, Optional

import requests


class NasaNeoClient:
  BASE_URL = "https://api.nasa.gov"

  def __init__(self, api_key: Optional[str] = None, timeout: int = 15):
      self.api_key = api_key or os.getenv("NASA_API_KEY")
      if not self.api_key:
          raise RuntimeError("NASA_API_KEY is not set")
      self.timeout = timeout

  def _get(self, path: str, **params: Any) -> Dict[str, Any]:
      url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
      params["api_key"] = self.api_key
      resp = requests.get(url, params=params, timeout=self.timeout)
      resp.raise_for_status()
      return resp.json()

  def fetch_feed(self, start_date: str, end_date: Optional[str] = None) -> Dict[str, Any]:
      params: Dict[str, Any] = {"start_date": start_date}
      if end_date:
          params["end_date"] = end_date
      return self._get("/neo/rest/v1/feed", **params)
