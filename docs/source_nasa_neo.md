# Source: NASA NEO API

## Overview

The NASA NeoWs (Near Earth Object Web Service) API provides data on near-Earth asteroids and their close-approach events to Earth.

- **API Base URL:** `https://api.nasa.gov/neo/rest/v1/`
- **Authentication:** API key (free at https://api.nasa.gov/)
- **Rate Limits:** 1,000 requests/hour with registered key; 30 requests/hour without

---

## Endpoints Used

### Feed Endpoint
```
GET /feed?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&api_key=<KEY>
```
Returns all near-Earth objects with close-approach data for the given date range.
- Maximum date range per request: 7 days
- Returns ~10–20 unique NEOs per day on average

---

## Key Fields

| Field | Type | Description |
|---|---|---|
| `id` | string | NASA internal NEO ID (maps to `neo_id`) |
| `neo_reference_id` | string | Reference ID |
| `name` | string | Common name |
| `absolute_magnitude_h` | float | Absolute magnitude (brightness proxy) |
| `estimated_diameter` | object | Min/max diameter in km, m, miles, feet |
| `is_potentially_hazardous_asteroid` | bool | NASA hazard flag |
| `is_sentry_object` | bool | Sentry impact monitoring flag |
| `close_approach_data[]` | array | One or more close-approach events |
| → `close_approach_date` | date | Date of close approach |
| → `close_approach_date_full` | string | Full datetime string |
| → `epoch_date_close_approach` | long | Unix epoch milliseconds |
| → `relative_velocity` | object | km/s, km/h, mph |
| → `miss_distance` | object | km, lunar, astronomical, miles |
| → `orbiting_body` | string | Body being orbited (usually "Earth") |

---

## Bronze Storage

Each close-approach event is stored as one row in `bronze.nasa_neo_event_raw`.  
`relative_velocity`, `miss_distance`, and `estimated_diameter` are stored as JSONB.

Unique constraint: `(neo_id, close_approach_date_full, orbiting_body)`

---

## Silver Transformation

- `silver.neo` — dimension table; one row per unique `neo_id`
- `silver.neo_close_approach` — fact table; one row per close-approach event; JSONB fields extracted to typed columns

---

## Notes

- The API returns all close approaches within the 7-day window; for historical backfills, the ingestor chunks requests into ≤7-day windows.
- Diameter is derived from absolute magnitude via Bond albedo model in the synthetic generator.
- `estimated_diameter` is a nested JSON with unit variants; the Spark job parses `kilometers` sub-object.

---

# Source Analysis

## What Data We Have

In this platform, NASA NeoWs is the **primary source**. From the `feed` endpoint we
capture, for each near-Earth object:

- **Object identity & physical attributes:** `neo_id`, `neo_reference_id`, `name`,
  `absolute_magnitude_h` (brightness proxy), `estimated_diameter` (min/max), and NASA's
  `is_potentially_hazardous_asteroid` / `is_sentry_object` flags.
- **Close-approach events:** for each pass, the date/time, `relative_velocity`,
  `miss_distance` (km / lunar distances / astronomical units), and `orbiting_body`.

Bronze (`bronze.nasa_neo_event_raw`) keeps one row per close-approach event with the full
raw JSON; silver splits this into a NEO dimension (`silver.neo`) and a close-approach fact
(`silver.neo_close_approach`); gold exposes hazard and close-approach analytics.

---

## How It Aligns With and Differs From Real-World Use

### What is realistic
- **The data is genuinely from NASA/JPL.** The fields, hazard flags, and physical
  parameters are exactly what risk and science teams analyze.
- **Hazard & close-approach analytics are real tasks.** Counting approaches within X lunar
  distances, ranking potentially hazardous asteroids (PHAs), and trending discovery rates
  mirror real planetary-defense workflows.
- **The 7-day windowing and backfill chunking** reflect how the public API must actually be paged.

### Where it differs / simplifies
- **No orbit determination.** NeoWs serves NASA's *precomputed* close-approach predictions;
  it does not provide the orbital elements, observations, or covariance needed to compute
  impact probability ourselves. We consume hazard verdicts, we don't derive them.
- **Aggregated, not observational.** Real planetary defense starts from raw telescope
  detections (astrometry) fed to orbit-fitting systems — a layer NeoWs hides.
- **Simplified hazard model.** The boolean `is_potentially_hazardous_asteroid` is a coarse
  size+MOID threshold, not the probabilistic risk assessment used operationally (Sentry, NEODyS).
- **Synthetic augmentation & simulated streaming.** ~50 synthetic NEO events are seeded
  alongside ~40 real ones, and the "streaming" path is a Kafka simulation, not a live feed.
- **Rate-limited.** 1,000 req/hr (keyed) constrains historical backfill speed vs. a bulk dataset.

---

## Real-World Sources of This Data

| Source | Operator | Notes |
|---|---|---|
| **NASA NeoWs (NeoWs/NEO API)** | NASA JPL / SSD-CNEOS | The REST API used here. |
| **CNEOS** (Center for Near-Earth Object Studies) | NASA JPL | Authoritative close-approach tables, **Sentry** impact monitoring, Scout. |
| **JPL Small-Body Database (SBDB)** | NASA JPL | Orbital elements, physical params for all known small bodies. |
| **Minor Planet Center (MPC)** | IAU / Harvard-Smithsonian | Clearinghouse for all asteroid/comet observations and designations. |
| **NEODyS / NEOCC** | ESA / University of Pisa | European NEO coordination, independent risk list. |
| **Survey telescopes** | Catalina Sky Survey, Pan-STARRS, ATLAS, NEOWISE, (future **NEO Surveyor**, **Rubin/LSST**) | The discovery instruments feeding the catalogs. |

---

## How Ingestion Happens in the Real World

1. **Detection:** Survey telescopes (Catalina, Pan-STARRS, ATLAS) image the sky nightly and
   flag moving objects.
2. **Astrometry → MPC:** Positional measurements are reported to the Minor Planet Center,
   which links detections and issues designations.
3. **Orbit determination:** JPL (CNEOS) and ESA (NEODyS) fit orbits, compute close-approach
   geometry (MOID), and run impact-monitoring (Sentry/Scout) over a ~100-year horizon.
4. **Publication:** Results are exposed through CNEOS tables and the NeoWs API.
5. **Downstream consumption:** Agencies, researchers, and apps pull the API or bulk data for
   monitoring, visualization, and planetary-defense coordination (e.g., IAWN).

Our platform joins at step 4: we poll `feed` on a schedule (Airflow `neo_batch_dag`), land
raw events in bronze, and model them through silver/gold.

---

## Who Uses This Data

- **Planetary-defense organizations** — NASA PDCO, ESA PDO, IAWN, SMPAG.
- **Astronomers & researchers** — population studies, follow-up observation planning.
- **Space agencies & mission planners** — target selection for sample-return/deflection
  missions (e.g., OSIRIS-REx, DART, Hera, Hayabusa2).
- **Educators, media & app developers** — public dashboards and "asteroid near Earth today" apps.
- **Risk & insurance analysts** — long-horizon impact-risk context.

---

## Importance of This Source

- **Planetary defense:** NEO tracking is the basis for detecting and (potentially)
  deflecting an Earth-impacting asteroid — validated operationally by NASA's 2022 DART mission.
- **Free, authoritative, machine-readable:** NeoWs makes NASA-quality data programmatically
  accessible, enabling broad participation in NEO awareness.
- **Science value:** Close-approach passes are opportunities for radar/optical
  characterization of asteroid composition and structure.
- **Public awareness:** Transparent, accessible hazard data builds informed public
  understanding rather than sensationalism.

---

## UAE Market Relevance

- **UAE Space Agency:** The UAE has an approved **asteroid-belt mission (MBR Explorer)**
  targeting seven asteroids with a 2028 launch and a planned landing on **Justitia** (2034) —
  making asteroid/NEO data directly strategic to national science goals.
- **Space science ecosystem:** Institutions like the **UAE Space Agency**, **NYU Abu Dhabi**,
  and **Khalifa University** can use NeoWs for research, education, and outreach without
  procurement barriers.
- **Planetary-defense participation:** As a rising space nation, the UAE can contribute to
  international NEO coordination (IAWN/SMPAG); a local analytics platform on open NEO data
  demonstrates capability and supports policy engagement.
- **STEM & public engagement:** NEO dashboards align with the UAE's national STEM and
  space-awareness initiatives, supporting outreach in schools and science centers.
- **Regional astronomy:** The Gulf's clear desert skies and growing observatory interest make
  follow-up observation and NEO characterization a plausible regional contribution.
