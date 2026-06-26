"""
services/synthetic/stream_producer.py

Continuously emits synthetic space-object events to Kafka topics,
useful for local streaming tests and load simulation without hitting
real APIs or rate limits.

Usage (standalone):
    python -m services.synthetic.stream_producer
    python -m services.synthetic.stream_producer --neo-rate 5 --satcat-rate 10 --interval 2

Topics used:
    nasa_neo_raw         (same as NasaNeoStreamProducer)
    celestrak_satcat_raw (same as CelesTrakSatcatStreamProducer)
"""
import argparse
import time
from datetime import date
from typing import Any, Dict

from services.common.kafka_client import KafkaProducerClient
from services.common.logging_utils import get_logger
from services.synthetic.generators import generate_neo_event, generate_satcat_record

logger = get_logger(
    "synthetic.stream_producer",
    extra={"component": "synthetic_stream_producer", "run_id": "-"},
)

NEO_TOPIC = "nasa_neo_raw"
SATCAT_TOPIC = "celestrak_satcat_raw"


def _neo_to_stream_msg(row: Dict[str, Any]) -> Dict[str, Any]:
    """Re-shape a generated NEO row into the same envelope the live producer emits."""
    return {
        "neo_id": row["neo_id"],
        "neo_reference_id": row["neo_reference_id"],
        "neo_name": row["neo_name"],
        "is_potentially_hazardous_asteroid": row["is_potentially_hazardous_asteroid"],
        "absolute_magnitude_h": row["absolute_magnitude_h"],
        "estimated_diameter": row["estimated_diameter"],
        "close_approach_date": row["close_approach_date"],
        "close_approach_date_full": row["close_approach_date_full"],
        "epoch_date_close_approach": row["epoch_date_close_approach"],
        "relative_velocity": row["relative_velocity"],
        "miss_distance": row["miss_distance"],
        "orbiting_body": row["orbiting_body"],
        "raw_neo": row["raw_neo"],
    }


def _satcat_to_stream_msg(row: Dict[str, Any]) -> Dict[str, Any]:
    """Re-shape a generated SATCAT row into the same envelope the live producer emits."""
    from datetime import datetime
    return {
        "snapshot_group": row["snapshot_group"],
        "snapshot_timestamp": datetime.utcnow().isoformat(),
        "satcat": row["parsed_record"],
    }


def run_forever(
    neo_rate: int = 3,
    satcat_rate: int = 5,
    interval_sec: float = 5.0,
) -> None:
    """
    Emit `neo_rate` NEO events and `satcat_rate` SATCAT records every `interval_sec`.
    """
    kafka = KafkaProducerClient()
    today = date.today()
    norad_counter = 90000

    logger.info(
        "Starting synthetic stream producer",
        extra={"neo_rate": neo_rate, "satcat_rate": satcat_rate, "interval_sec": interval_sec},
    )

    while True:
        try:
            # --- NEO events ---
            for _ in range(neo_rate):
                row = generate_neo_event(approach_date=today, source="synthetic_stream")
                msg = _neo_to_stream_msg(row)
                kafka.send(NEO_TOPIC, value=msg, key=row["neo_id"])

            # --- SATCAT records ---
            for i in range(satcat_rate):
                row = generate_satcat_record(
                    norad_cat_id=norad_counter,
                    snapshot_date=today,
                    source="synthetic_stream",
                )
                msg = _satcat_to_stream_msg(row)
                kafka.send(SATCAT_TOPIC, value=msg, key=str(norad_counter))
                norad_counter += 1

            kafka.flush()
            logger.info(
                "Emitted synthetic batch",
                extra={"neo_count": neo_rate, "satcat_count": satcat_rate},
            )
        except Exception:
            logger.exception("Synthetic producer iteration failed")

        time.sleep(interval_sec)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Stream synthetic space-object data to Kafka.")
    parser.add_argument("--neo-rate", type=int, default=3, help="NEO events per interval")
    parser.add_argument("--satcat-rate", type=int, default=5, help="SATCAT records per interval")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between batches")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    run_forever(
        neo_rate=args.neo_rate,
        satcat_rate=args.satcat_rate,
        interval_sec=args.interval,
    )


if __name__ == "__main__":
    main()
