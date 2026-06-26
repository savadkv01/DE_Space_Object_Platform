"""
services/synthetic/generators.py

Generates realistic synthetic space-object records whose shape exactly
matches the existing bronze schema.  Uses only stdlib (random, math, uuid,
datetime) so no extra dependencies are required.

Record realism targets
----------------------
NEO close-approach events
  - absolute_magnitude_h  ~ Uniform(10, 35)  (most NEOs 18-28)
  - miss_distance_km      ~ LogNormal: median ~4 M km, range 50k – 70 M km
  - relative_velocity_km_s ~ Uniform(2, 72)
  - is_potentially_hazardous ~ True for ~15% of events
  - orbiting_body         99% Earth, 1% random solar-system body

CelesTrak SATCAT records
  - norad_cat_id          sequential from a random base
  - orbit types           LEO / MEO / GEO / HEO in realistic proportions
  - inclination_deg       correlated with orbit type
  - period_minutes        derived from altitude using simplified Kepler
  - apogee / perigee      rounded realistic altitude bands
  - owner                 weighted sample of real space agencies
  - object_type           PAYLOAD / ROCKET BODY / DEBRIS / TBA
"""

import math
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ORBIT_BODIES = ["Earth"] * 99 + ["Mars", "Venus", "Jupiter", "Moon"]
_OPERATORS = [
    "US", "US", "US", "RU", "RU", "CN", "CN", "ESA", "ESA",
    "ISRO", "JAXA", "UK", "FR", "DE", "IT", "CA", "AU",
]
_OBJECT_TYPES = ["PAYLOAD"] * 55 + ["ROCKET BODY"] * 20 + ["DEBRIS"] * 22 + ["TBA"] * 3
_OPS_STATUSES = ["+", "+", "+", "+", "+", "-", "P", "B", "D"]

# Realistic orbit altitude bands (km above Earth surface)
_ORBIT_BANDS = {
    "LEO": (200, 2000),    # ~68% of catalog
    "MEO": (2000, 35786),  # ~8%
    "GEO": (35786, 35786), # ~10% (geostationary – apogee ≈ perigee)
    "HEO": (400, 40000),   # ~14% (high eccentricity)
}
_ORBIT_WEIGHTS = [0.68, 0.08, 0.10, 0.14]

_EARTH_RADIUS_KM = 6371.0
_MU_KM3_S2 = 398600.4418  # Earth's gravitational parameter

# ---------------------------------------------------------------------------
# NEO generators
# ---------------------------------------------------------------------------


def _rand_neo_id() -> str:
    return str(random.randint(2_000_000, 9_999_999))


def _log_normal(median: float, sigma: float) -> float:
    mu = math.log(median)
    return math.exp(random.gauss(mu, sigma))


def _neo_diameter(abs_mag: float) -> Dict[str, Any]:
    """Approximate diameter from H magnitude using Bond albedo = 0.154."""
    albedo = 0.154
    d_km = (1329.0 / math.sqrt(albedo)) * 10 ** (-abs_mag / 5.0)
    # typical 20% uncertainty band
    d_min = round(d_km * 0.8, 6)
    d_max = round(d_km * 1.2, 6)
    d_min_m, d_max_m = d_min * 1000, d_max * 1000
    d_min_mi, d_max_mi = d_min * 0.621371, d_max * 0.621371
    d_min_ft, d_max_ft = d_min_m * 3.28084, d_max_m * 3.28084
    return {
        "kilometers": {"estimated_diameter_min": d_min, "estimated_diameter_max": d_max},
        "meters": {"estimated_diameter_min": d_min_m, "estimated_diameter_max": d_max_m},
        "miles": {"estimated_diameter_min": d_min_mi, "estimated_diameter_max": d_max_mi},
        "feet": {"estimated_diameter_min": d_min_ft, "estimated_diameter_max": d_max_ft},
    }


def generate_neo_event(
    approach_date: Optional[date] = None,
    neo_id: Optional[str] = None,
    source: str = "synthetic",
) -> Dict[str, Any]:
    """Return one synthetic NEO close-approach event matching bronze.nasa_neo_event_raw."""
    if approach_date is None:
        approach_date = date.today() - timedelta(days=random.randint(0, 365))
    if neo_id is None:
        neo_id = _rand_neo_id()

    abs_mag = round(random.uniform(10.0, 35.0), 2)
    is_hazardous = random.random() < 0.15
    miss_km = round(_log_normal(4_000_000, 0.9), 2)
    miss_lunar = round(miss_km / 384_400, 4)
    miss_au = round(miss_km / 1.496e8, 9)
    miss_miles = round(miss_km * 0.621371, 2)
    vel_km_s = round(random.uniform(2.0, 72.0), 3)
    vel_km_h = round(vel_km_s * 3600, 3)
    vel_mi_h = round(vel_km_h * 0.621371, 3)
    orbiting_body = random.choice(_ORBIT_BODIES)
    approach_dt = datetime.combine(approach_date, datetime.min.time())
    approach_dt = approach_dt.replace(
        hour=random.randint(0, 23), minute=random.randint(0, 59)
    )
    approach_date_full = approach_dt.strftime("%Y-%b-%d %H:%M")
    epoch_ms = int(approach_dt.timestamp() * 1000)

    estimated_diameter = _neo_diameter(abs_mag)
    neo_name = f"({neo_id}) {random.randint(1900, 2024)} {random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{random.randint(1, 99)}"

    raw_neo: Dict[str, Any] = {
        "id": neo_id,
        "neo_reference_id": neo_id,
        "name": neo_name,
        "is_potentially_hazardous_asteroid": is_hazardous,
        "absolute_magnitude_h": abs_mag,
        "estimated_diameter": estimated_diameter,
        "close_approach_data": [
            {
                "close_approach_date": approach_date.isoformat(),
                "close_approach_date_full": approach_date_full,
                "epoch_date_close_approach": epoch_ms,
                "relative_velocity": {
                    "kilometers_per_second": str(vel_km_s),
                    "kilometers_per_hour": str(vel_km_h),
                    "miles_per_hour": str(vel_mi_h),
                },
                "miss_distance": {
                    "astronomical": str(miss_au),
                    "lunar": str(miss_lunar),
                    "kilometers": str(miss_km),
                    "miles": str(miss_miles),
                },
                "orbiting_body": orbiting_body,
            }
        ],
        "_synthetic": True,
        "_source": source,
    }

    return {
        "feed_start_date": approach_date.isoformat(),
        "feed_end_date": approach_date.isoformat(),
        "neo_id": neo_id,
        "neo_reference_id": neo_id,
        "neo_name": neo_name,
        "is_potentially_hazardous_asteroid": is_hazardous,
        "absolute_magnitude_h": abs_mag,
        "estimated_diameter": estimated_diameter,
        "close_approach_date": approach_date.isoformat(),
        "close_approach_date_full": approach_date_full,
        "epoch_date_close_approach": epoch_ms,
        "relative_velocity": {
            "kilometers_per_second": str(vel_km_s),
            "kilometers_per_hour": str(vel_km_h),
            "miles_per_hour": str(vel_mi_h),
        },
        "miss_distance": {
            "astronomical": str(miss_au),
            "lunar": str(miss_lunar),
            "kilometers": str(miss_km),
            "miles": str(miss_miles),
        },
        "orbiting_body": orbiting_body,
        "raw_neo": raw_neo,
    }


def generate_neo_batch(
    n: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    source: str = "synthetic",
) -> List[Dict[str, Any]]:
    """Return n synthetic NEO events spread across a date range."""
    if start_date is None:
        start_date = date.today() - timedelta(days=30)
    if end_date is None:
        end_date = date.today()
    span = (end_date - start_date).days or 1
    return [
        generate_neo_event(
            approach_date=start_date + timedelta(days=random.randint(0, span)),
            source=source,
        )
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# SATCAT generators
# ---------------------------------------------------------------------------


def _period_from_altitude(alt_km: float) -> float:
    """Orbital period in minutes from mean altitude (simplified circular orbit)."""
    r = _EARTH_RADIUS_KM + alt_km
    period_s = 2 * math.pi * math.sqrt(r**3 / _MU_KM3_S2)
    return round(period_s / 60, 3)


def _inclination_for_orbit(orbit_type: str) -> float:
    if orbit_type == "GEO":
        return round(random.gauss(0.05, 0.1), 2)
    if orbit_type == "MEO":
        return round(random.uniform(0, 65), 2)
    if orbit_type == "HEO":
        return round(random.uniform(0, 120), 2)
    # LEO – sun-synchronous band around 98° is common
    return round(random.choice(
        [random.uniform(0, 55), random.gauss(98, 1), random.uniform(85, 100)]
    ), 2)


def generate_satcat_record(
    norad_cat_id: int,
    snapshot_date: Optional[date] = None,
    snapshot_group: str = "active",
    source: str = "synthetic",
) -> Dict[str, Any]:
    """Return one synthetic SATCAT record matching bronze.celestrak_satcat_raw."""
    if snapshot_date is None:
        snapshot_date = date.today()

    orbit_type = random.choices(
        list(_ORBIT_BANDS.keys()), weights=_ORBIT_WEIGHTS, k=1
    )[0]
    alt_lo, alt_hi = _ORBIT_BANDS[orbit_type]
    if orbit_type == "GEO":
        perigee = apogee = 35786
    elif orbit_type == "HEO":
        perigee = random.randint(200, 1000)
        apogee = random.randint(20000, 40000)
    else:
        perigee = random.randint(alt_lo, min(alt_lo + 800, alt_hi))
        apogee = perigee + random.randint(0, 300)

    mean_alt = (perigee + apogee) / 2
    period = _period_from_altitude(mean_alt)
    inclination = _inclination_for_orbit(orbit_type)
    ecc = round((apogee - perigee) / (2 * (_EARTH_RADIUS_KM + mean_alt)), 7)
    mean_motion = round(1440 / period, 8)

    launch_year = random.randint(1957, date.today().year)
    launch_month = random.randint(1, 12)
    launch_date = date(launch_year, launch_month, random.randint(1, 28))
    intl_desig = f"{launch_year % 100:02d}{random.randint(1, 300):03d}{random.choice('ABCDEFGHJK')}"
    object_name = f"SYNTH-OBJ-{norad_cat_id}"
    obj_type = random.choice(_OBJECT_TYPES)
    owner = random.choice(_OPERATORS)
    ops_status = random.choice(_OPS_STATUSES)

    parsed: Dict[str, Any] = {
        "NORAD_CAT_ID": str(norad_cat_id),
        "INTLDES": intl_desig,
        "OBJECT_NAME": object_name,
        "OBJECT_TYPE": obj_type,
        "OWNER": owner,
        "OPS_STATUS_CODE": ops_status,
        "LAUNCH": launch_date.isoformat(),
        "LAUNCH_YEAR": str(launch_year),
        "PERIOD": str(period),
        "INCLINATION": str(inclination),
        "APOGEE": str(apogee),
        "PERIGEE": str(perigee),
        "ECC": str(ecc),
        "MEAN_MOTION": str(mean_motion),
        "ORBIT_TYPE": orbit_type,
        "_synthetic": "true",
        "_source": source,
    }

    raw_csv_row = ",".join(str(parsed.get(f, "")) for f in [
        "NORAD_CAT_ID", "INTLDES", "OBJECT_NAME", "OBJECT_TYPE",
        "OWNER", "OPS_STATUS_CODE", "LAUNCH", "PERIOD",
        "INCLINATION", "APOGEE", "PERIGEE", "ECC", "MEAN_MOTION",
    ])

    return {
        "snapshot_group": snapshot_group,
        "snapshot_date": snapshot_date.isoformat(),
        "raw_csv_row": raw_csv_row,
        "parsed_record": parsed,
    }


def generate_satcat_batch(
    n: int = 200,
    snapshot_date: Optional[date] = None,
    snapshot_group: str = "active",
    norad_start: int = 90000,
    source: str = "synthetic",
) -> List[Dict[str, Any]]:
    """Return n synthetic SATCAT records."""
    if snapshot_date is None:
        snapshot_date = date.today()
    return [
        generate_satcat_record(
            norad_cat_id=norad_start + i,
            snapshot_date=snapshot_date,
            snapshot_group=snapshot_group,
            source=source,
        )
        for i in range(n)
    ]
