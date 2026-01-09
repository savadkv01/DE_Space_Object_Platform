from abc import ABC, abstractmethod
import requests
from typing import Any, Dict

class ApiClient(ABC):
    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    def build_params(self, **kwargs) -> Dict[str, Any]:
        ...

    def get(self, path: str, **params) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        query = self.build_params(**params)
        resp = requests.get(url, params=query, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()