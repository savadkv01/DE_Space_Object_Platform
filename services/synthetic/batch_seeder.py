"""
services/synthetic/batch_seeder.py

Seeds bronze tables directly via DbClient.

Usage (standalone):
    python -m services.synthetic.batch_seeder --neo 200 --satcat 300
    python -m services.synthetic.batch_seeder --neo 200 --satcat 300 \
        --start-date 2025-01-01 --end-date 2025-12-31

All seeded rows are marked with _synthetic=true in raw_neo/parsed_record
so real data is never polluted.
"""
import argparse
import sys
from datetime import date, datetime
from typing import List, Dict, Any

from services.common.db_client import DbClient
from services.common.logging_utils import get_logger
from services.synthetic.generators import generate_neo_batch, generate_satcat_batch

logger = get_logger("synthetic.batch_seeder", extra={"component": "batch_seeder", "run_id": "-"})


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

_NEO_SQL = """
INSERT INTO bronze.nasa_neo_event_raw (
    feed_start_date, feed_end_date,
    neo_id, neo_reference_id, neo_name,
    is_potentially_hazardous_asteroid, absolute_magnitude_h,
    estimated_diameter,
    close_approach_date, close_approach_date_full, epoch_date_close_approach,
    relative_velocity, miss_distance, orbiting_body, raw_neo
)
VALUES (
    %(feed_start_date)s, %(feed_end_date)s,
    %(neo_id)s, %(neo_reference_id)s, %(neo_name)s,
    %(is_potentially_hazardous_asteroid)s, %(absolute_magnitude_h)s,
    %(estimated_diameter)s,
    %(close_approach_date)s, %(close_approach_date_full)s, %(epoch_date_close_approach)s,
    %(relative_velocity)s, %(miss_distance)s, %(orbiting_body)s, %(raw_neo)s
)
ON CONFLICT (neo_id, close_approach_date_full, orbiting_body) DO NOTHING;
"""

_SATCAT_SQL = """
INSERT INTO bronze.celestrak_satcat_raw (
    snapshot_group, snapshot_date, raw_csv_row, parsed_record
)
VALUES (
    %(snapshot_group)s, %(snapshot_date)s, %(raw_csv_row)s, %(parsed_record)s
);
"""


def seed_neo(db: DbClient, rows: List[Dict[str, Any]]) -> int:
    count = db.executemany(_NEO_SQL, rows)
    logger.info("Seeded NEO events", extra={"count": count})
    return count


def seed_satcat(db: DbClient, rows: List[Dict[str, Any]]) -> int:
    count = db.executemany(_SATCAT_SQL, rows)
    logger.info("Seeded SATCAT records", extra={"count": count})
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Seed bronze tables with synthetic data.")
    parser.add_argument("--neo", type=int, default=100, help="Number of NEO events to seed")
    parser.add_argument("--satcat", type=int, default=200, help="Number of SATCAT records to seed")
    parser.add_argument("--start-date", default=None, help="NEO start date YYYY-MM-DD (default: 30 days ago)")
    parser.add_argument("--end-date", default=None, help="NEO end date YYYY-MM-DD (default: today)")
    parser.add_argument("--snapshot-date", default=None, help="SATCAT snapshot date YYYY-MM-DD (default: today)")
    parser.add_argument("--norad-start", type=int, default=90000, help="Starting NORAD CAT ID for synthetic satellites")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)

    start_date = date.fromisoformat(args.start_date) if args.start_date else None
    end_date = date.fromisoformat(args.end_date) if args.end_date else None
    snapshot_date = date.fromisoformat(args.snapshot_date) if args.snapshot_date else None

    db = DbClient()

    if args.neo > 0:
        neo_rows = generate_neo_batch(n=args.neo, start_date=start_date, end_date=end_date)
        seed_neo(db, neo_rows)

    if args.satcat > 0:
        satcat_rows = generate_satcat_batch(
            n=args.satcat,
            snapshot_date=snapshot_date,
            norad_start=args.norad_start,
        )
        seed_satcat(db, satcat_rows)

    logger.info("Batch seeding complete", extra={"neo": args.neo, "satcat": args.satcat})


if __name__ == "__main__":
    main()
