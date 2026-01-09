from datetime import date
from typing import Any, Dict, Iterable, Optional

from services.ingestion.nasa_neo.neo_client import NasaNeoClient
from services.common.streaming_base import BaseStreamingProducer


class NasaNeoStreamProducer(BaseStreamingProducer):
    """
    Periodically fetches NASA NEO feed for today and emits one Kafka message
    per close-approach event.

    Topic: nasa_neo_raw
    """

    def __init__(self, poll_interval_sec: int = 300) -> None:
        super().__init__(topic="nasa_neo_raw", poll_interval_sec=poll_interval_sec)
        self.client = NasaNeoClient()

    def extract(self) -> Dict[str, Any]:
        today = date.today().strftime("%Y-%m-%d")
        self.logger.info("Fetching NEO feed for streaming", extra={"date": today})
        return self.client.fetch_feed(start_date=today, end_date=today)

    def transform(self, raw: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        neo_by_date = raw.get("near_earth_objects", {})
        for approach_date, neos in neo_by_date.items():
            for neo in neos:
                neo_id = neo.get("id")
                neo_ref_id = neo.get("neo_reference_id")
                neo_name = neo.get("name")
                is_hazardous = neo.get("is_potentially_hazardous_asteroid")
                abs_mag = neo.get("absolute_magnitude_h")
                est_diam = neo.get("estimated_diameter")

                for cad in neo.get("close_approach_data", []):
                    yield {
                        "neo_id": neo_id,
                        "neo_reference_id": neo_ref_id,
                        "neo_name": neo_name,
                        "is_potentially_hazardous_asteroid": is_hazardous,
                        "absolute_magnitude_h": abs_mag,
                        "estimated_diameter": est_diam,
                        "close_approach_date": cad.get("close_approach_date"),
                        "close_approach_date_full": cad.get("close_approach_date_full"),
                        "epoch_date_close_approach": cad.get("epoch_date_close_approach"),
                        "relative_velocity": cad.get("relative_velocity"),
                        "miss_distance": cad.get("miss_distance"),
                        "orbiting_body": cad.get("orbiting_body"),
                        "raw_neo": neo,
                    }

    def get_key(self, msg: Dict[str, Any]) -> Optional[str]:
        # Use neo_id as Kafka key for better partitioning
        return msg.get("neo_id")


def main():
    producer = NasaNeoStreamProducer(poll_interval_sec=300)  # every 5 minutes
    producer.run_forever()


if __name__ == "__main__":
    main()
