# Source Analysis: CelesTrak (SATCAT & TLE)

## 1. Overview

[CelesTrak](https://celestrak.org/) is a long-running, freely accessible source of
satellite orbital data maintained by Dr. T.S. Kelso. In this platform it is the
**secondary source**, providing the satellite catalog (SATCAT) and Two-Line Element
(TLE) data that power the satellite-population and orbital-regime analytics.

- **Provider:** CelesTrak (independent, originally affiliated with AGI / Ansys)
- **Base URL:** `https://celestrak.org`
- **SATCAT endpoint used:** `GET /satcat/records.php?GROUP=<group>&FORMAT=csv`
- **Authentication:** None (public, no API key)
- **Cost:** Free
- **Default group ingested:** `active` (configurable in `services/ingestion/celestrak/config.yaml`)
- **Update cadence (upstream):** SATCAT refreshed daily; TLEs refreshed multiple times per day
- **Format:** CSV (SATCAT), 3-line text blocks (TLE)

CelesTrak ultimately republishes data that originates from the **U.S. Space Force
18th/19th Space Defense Squadron** (formerly JSpOC/Space-Track), making it a
convenient, key-free mirror of the authoritative U.S. catalog.

---

## 2. What Data We Have

### 2.1 SATCAT (Satellite Catalog) — primary feed in this platform

Each CSV record describes one tracked object. The fields we parse into the silver
layer (see [bronze_to_silver_celestrak.py](../spark_jobs/bronze_to_silver_celestrak.py)):

| CSV Field | Silver Column | Description |
|---|---|---|
| `NORAD_CAT_ID` | `norad_cat_id` | Unique catalog number assigned by U.S. Space Command |
| `OBJECT_ID` | `object_id` | International designator (COSPAR ID), e.g. `2020-061A` |
| `OBJECT_NAME` | `object_name` | Common object name |
| `OBJECT_TYPE` | `object_type` | PAYLOAD / ROCKET BODY / DEBRIS / UNKNOWN |
| `OWNER` | `owner` | Country/organization code (e.g. `US`, `UAE`, `PRC`) |
| `OPS_STATUS_CODE` | `ops_status_code` | Operational status (+, -, D, etc.) |
| `LAUNCH_DATE` | `launch_date` | Launch date |
| `LAUNCH_SITE` | `launch_site` | Launch site code |
| `DECAY_DATE` | `decay_date` | Re-entry/decay date (null if on orbit) |
| `ORBIT_CENTER` | `orbit_center` | Body being orbited (e.g. EA = Earth) |
| `ORBIT_TYPE` | `orbit_type` | Orbit classification (ORB, IMP, etc.) |
| `RCS` | `rcs` | Radar cross-section (m²) — size proxy |
| `PERIOD` | `period_minutes` | Orbital period (minutes) |
| `INCLINATION` | `inclination_deg` | Orbital inclination (degrees) |
| `APOGEE` | `apogee_km` | Apogee altitude (km) |
| `PERIGEE` | `perigee_km` | Perigee altitude (km) |

**Bronze storage:** `bronze.celestrak_satcat_raw` — one row per CSV record, storing
both the `raw_csv_row` (text) and the `parsed_record` (JSONB). A snapshot is keyed by
`(snapshot_group, snapshot_date)` and ingestion is idempotent: if a snapshot for that
group+date already exists, the load is skipped.

**Silver tables:**
- `silver.satcat_satellite` — dimension, one row per `norad_cat_id` with first/last seen dates.
- `silver.satcat_orbit_snapshot` — fact, one row per `(norad_cat_id, snapshot_date)`, enabling
  time-series analysis of how orbital elements (apogee, perigee, inclination, period) drift over time.

### 2.2 TLE (Two-Line Element sets) — modeled, lighter usage

The schema reserves `bronze.celestrak_tle_raw` (one row per 3-line TLE block:
`line0` name, `line1`, `line2`, plus `norad_cat_id`). TLEs encode the mean orbital
elements needed by the SGP4 propagator to predict a satellite's position at any future
time. SATCAT is the catalog of *what* exists; TLEs are the time-varying *where it is*.

---

## 3. How It Aligns With and Differs From Real-World Use

### 3.1 What is realistic
- **The catalog structure is real.** `NORAD_CAT_ID`, COSPAR `OBJECT_ID`, owner codes,
  orbit classification, apogee/perigee/inclination/period are exactly the fields
  operators and analysts work with.
- **The orbital-regime analytics are real.** Deriving LEO/MEO/GEO buckets from
  apogee/perigee, counting debris vs. payloads, and tracking population growth are
  genuine space-situational-awareness (SSA) tasks.
- **Snapshot-over-time modeling is real.** Comparing daily SATCAT snapshots to detect
  catalog changes, decays, and new launches mirrors how SSA teams monitor the catalog.

### 3.2 Where it differs / simplifies
- **No live conjunction screening.** Real SSA performs continuous close-approach
  (conjunction) screening between thousands of objects using full ephemerides and
  covariance data. Here we model the *catalog*, not real-time collision risk.
- **Mean elements only, not precision ephemerides.** TLE/SATCAT elements are low-precision
  mean elements (accuracy degrades within days). Operational collision avoidance uses
  high-precision Special Perturbations (SP) ephemerides and owner-operator GPS data not
  present in public feeds.
- **Public catalog is filtered.** Sensitive/classified national-security payloads are
  withheld or have degraded elements in the public catalog.
- **Snapshot, not streaming truth.** Our streaming path is *simulated* via Kafka; the real
  catalog updates as sensor observations arrive at the 18th SDS, not on our poll cadence.
- **Synthetic augmentation.** ~100 synthetic SATCAT records are seeded alongside the real
  306k+ records for demo/streaming purposes and are flagged as synthetic.

---

## 4. Real-World Sources of This Data

CelesTrak is one mirror in a broader ecosystem:

| Source | Operator | Notes |
|---|---|---|
| **Space-Track.org** | U.S. Space Force (18th/19th SDS) | The authoritative catalog; requires a (free) account and agreeing to terms. Provides SATCAT, TLEs, SP ephemerides, conjunction data messages (CDMs). |
| **CelesTrak** | T.S. Kelso (independent) | Key-free republisher with grouped feeds, GP/OMM data, supplemental operator TLEs. *(Used here.)* |
| **NORAD/USSPACECOM** | U.S. DoD | Originates the catalog from the Space Surveillance Network (SSN) radar/optical sensors. |
| **ESA Space Debris Office / DISCOS** | European Space Agency | Independent debris database and modeling (MASTER, DRAMA). |
| **EU SST / EUSST** | EU consortium | European SSA service for collision avoidance, re-entry, fragmentation. |
| **Commercial SSA** | LeoLabs, Slingshot Aerospace, ExoAnalytic, COMSPOC | Independent radar/optical networks selling higher-precision tracking and conjunction services. |
| **Operator ephemerides** | Satellite operators | High-accuracy GPS-derived state vectors shared via Space-Track / SDA. |

---

## 5. How Ingestion Happens in the Real World

1. **Observation:** Ground-based radars and optical telescopes (the Space Surveillance
   Network; commercial networks like LeoLabs) and space-based sensors observe objects.
2. **Orbit determination:** Observations are correlated to known objects and fitted to
   produce updated orbital elements (mean elements → TLE; precise → SP ephemerides).
3. **Catalog maintenance:** The 18th/19th SDS maintains the master catalog, assigns
   `NORAD_CAT_ID` and COSPAR IDs, and flags status (active, decayed, debris).
4. **Publication:** Data is published to Space-Track (authoritative) and mirrored/curated
   by CelesTrak. TLEs update several times daily; high-interest objects more often.
5. **Downstream consumption:** Operators ingest TLEs/ephemerides into flight-dynamics
   systems and propagators (SGP4/SDP4 or numerical integrators) for tracking, planning,
   and conjunction assessment; CDMs are issued when close approaches are predicted.

In this platform that pipeline is compressed: we poll the CelesTrak SATCAT CSV on a
schedule (Airflow `celestrak_batch_dag`), land it in bronze, and transform to silver/gold —
skipping orbit determination and conjunction screening, which are out of scope.

---

## 6. Who Uses This Data

- **Satellite operators** (commercial, government, military) — collision avoidance,
  station-keeping, maneuver planning, re-entry prediction.
- **Space agencies** (NASA, ESA, UAE Space Agency, ISRO, etc.) — mission planning, debris
  mitigation, space sustainability policy.
- **Launch providers & insurers** — slot/orbit deconfliction and risk assessment.
- **Astronomers** — predicting and mitigating satellite streaks (e.g., Starlink) in observations.
- **Defense/SSA organizations** — space domain awareness and threat monitoring.
- **Researchers & academia** — debris-environment modeling, orbital-regime studies.
- **Hobbyists** — satellite tracking, amateur radio, visual pass prediction.

---

## 7. Importance of This Source

- **Space sustainability:** With 30,000+ tracked objects and millions of untracked
  fragments, the catalog underpins collision avoidance and the long-term usability of
  key orbits (the Kessler-syndrome risk).
- **Asset protection:** Operators rely on it to protect multi-hundred-million-dollar
  satellites and crewed platforms (ISS maneuvers use this data).
- **Transparency & accessibility:** Being free and key-free, CelesTrak democratizes SSA
  data for academia, startups, and emerging space nations.
- **Foundation for analytics:** Population growth, mega-constellation impact, and
  orbital-regime congestion analysis all start from this catalog.

---

## 8. UAE Market Relevance

The UAE has a fast-growing space sector for which satellite-catalog analytics are directly
applicable:

- **UAE Space Agency (UAESA):** Establishing national space situational awareness and a
  regulatory/space-sustainability framework; SATCAT analytics support licensing, debris
  mitigation policy, and registry obligations for UAE-owned objects (`OWNER = UAE`).
- **MBRSC (Mohammed Bin Rashid Space Centre):** Operates Earth-observation satellites
  (**KhalifaSat**, **DubaiSat-1/2**) and the **MBZ-SAT**; needs conjunction awareness and
  orbital monitoring for its LEO assets.
- **GEO communications operators (Yahsat, Thuraya):** Operate geostationary
  communications satellites where slot management and collision avoidance in the congested
  GEO belt are commercially critical.
- **National registry & compliance:** Filtering the catalog by `OWNER = UAE` provides an
  inventory of UAE-registered objects to support UN Registration Convention reporting and
  the UAE's space-debris regulations.
- **New-space & academia:** University CubeSat programs (e.g., **MeznSat**, Khalifa
  University, NYU Abu Dhabi) and startups can use this open data for tracking, education,
  and SSA research without procurement barriers.
- **Strategic positioning:** As the UAE positions itself as a regional space hub (Mars
  mission, lunar rover Rashid, asteroid-belt mission to **Justitia**), domestic SSA
  capability built on open catalog data strengthens sovereignty and safety-of-flight.

---

## 9. Configuration & Operational Notes

- **Client:** [celestrak_client.py](../services/ingestion/celestrak/celestrak_client.py)
  — `GET /satcat/records.php?GROUP=active&FORMAT=csv` with retry/backoff on 429/5xx.
- **Ingestor:** [celestrak_batch_ingestor.py](../services/ingestion/celestrak/celestrak_batch_ingestor.py)
  — idempotent per `(snapshot_group, snapshot_date)`.
- **Config:** [config.yaml](../services/ingestion/celestrak/config.yaml) — `default_group: active`,
  streaming `poll_interval_sec: 600`, Kafka topic `celestrak_satcat_raw`.
- **Etiquette:** CelesTrak is donation-supported and rate-limited; avoid aggressive polling.
  SATCAT changes at most daily, so the idempotent daily snapshot is appropriate.
- **Volume:** ~306k real records per full-catalog snapshot (`GROUP=active` is a subset);
  see repository data counts.
