import csv
from datetime import datetime
from io import StringIO
from typing import Any, Dict, Iterable, Optional

from services.ingestion.celestrak.celestrak_client import CelesTrakClient
from services.common.streaming_base import BaseStreamingProducer


class CelesTrakSatcatStreamProducer(BaseStreamingProducer):
    """
    Periodically fetches CelesTrak SATCAT CSV for GROUP=active and emits
    one Kafka message per satellite record.

    Topic: celestrak_satcat_raw
    """

    def __init__(self, group: str = "active", poll_interval_sec: int = 600) -> None:
        super().__init__(topic="celestrak_satcat_raw", poll_interval_sec=poll_interval_sec)
        self.client = CelesTrakClient()
        self.group = group

    def extract(self) -> str:
        self.logger.info("Fetching SATCAT CSV for streaming", extra={"group": self.group})
        return self.client.fetch_satcat_csv(self.group)

    def transform(self, raw_csv: str) -> Iterable[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        f = StringIO(raw_csv)
        reader = csv.DictReader(f)
        for row in reader:
            yield {
                "snapshot_group": self.group,
                "snapshot_timestamp": now,
                "satcat": row,
            }

    def get_key(self, msg: Dict[str, Any]) -> Optional[str]:
        satcat = msg.get("satcat") or {}
        return satcat.get("NORAD_CAT_ID")


def main():
    producer = CelesTrakSatcatStreamProducer(group="active", poll_interval_sec=600)
    producer.run_forever()


if __name__ == "__main__":
    main()
