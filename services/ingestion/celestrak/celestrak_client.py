import requests

class CelesTrakClient:
    def __init__(self, base_url: str = "https://celestrak.org"):
        self.base_url = base_url.rstrip("/")

    def fetch_satcat_csv(self, group: str = "active") -> str:
        url = f"{self.base_url}/satcat/records.php"
        resp = requests.get(url, params={"GROUP": group, "FORMAT": "csv"}, timeout=20)
        resp.raise_for_status()
        return resp.text

    def fetch_tle(self, group: str = "active") -> str:
        url = f"{self.base_url}/NORAD/elements/gp.php"
        resp = requests.get(url, params={"GROUP": group, "FORMAT": "tle"}, timeout=20)
        resp.raise_for_status()
        return resp.text