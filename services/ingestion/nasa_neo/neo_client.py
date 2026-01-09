class NasaNeoClient(ApiClient):
    def build_params(self, **kwargs) -> Dict[str, Any]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def fetch_feed(self, start_date: str, end_date: str | None = None) -> dict:
        return self.get("/neo/rest/v1/feed", start_date=start_date, end_date=end_date)

    def fetch_neo(self, neo_id: str) -> dict:
        return self.get(f"/neo/rest/v1/neo/{neo_id}")