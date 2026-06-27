# Source Data Overview

This document is the entry point for understanding the external data sources that feed the
Space Object Situational Awareness Platform. Each source has a dedicated deep-dive analysis;
this page summarizes both and the cross-cutting context.

| | NASA NeoWs | CelesTrak |
|---|---|---|
| **Role** | Primary source | Secondary source |
| **Domain** | Near-Earth objects (asteroids) | Satellites & orbital catalog |
| **Deep-dive** | [source_nasa_neo.md](source_nasa_neo.md) | [source_celestrak.md](source_celestrak.md) |
| **Base URL** | `https://api.nasa.gov/neo/rest/v1/` | `https://celestrak.org` |
| **Auth** | Free API key | None |
| **Format** | JSON | CSV (SATCAT) / TXT (TLE) |
| **Cadence** | Daily feed (≤7-day windows) | Daily SATCAT snapshot |
| **Bronze table** | `bronze.nasa_neo_event_raw` | `bronze.celestrak_satcat_raw` |
| **Silver tables** | `silver.neo`, `silver.neo_close_approach` | `silver.satcat_satellite`, `silver.satcat_orbit_snapshot` |
| **Authoritative origin** | NASA JPL / CNEOS | U.S. Space Force 18th/19th SDS (via Space-Track) |

---

## What These Two Sources Together Enable

The platform combines **two complementary views of objects in space**:

- **Natural objects (NEOs):** asteroids approaching Earth — a *planetary-defense* domain.
- **Artificial objects (satellites/debris):** the human-made catalog — a *space-situational-awareness* domain.

Together they support the platform's stated personas: risk/operations teams monitoring
hazards, data scientists modeling orbital dynamics, and BI teams building population and
close-approach dashboards (see [scope.md](scope.md)).

---

## Cross-Cutting: Real-World vs. This Platform

- **We consume curated outputs, not raw observations.** Both NASA and CelesTrak republish
  the results of upstream observation + orbit-determination pipelines. We do not perform
  telescope astrometry, radar tracking, or orbit fitting — those steps are out of scope.
- **Streaming is simulated.** Real catalogs update as sensor data arrives; here the streaming
  path is a Kafka simulation layered on scheduled batch polls.
- **Synthetic augmentation.** A small set of synthetic NEO and SATCAT records is seeded
  alongside the real data (and flagged as synthetic) to exercise streaming and demos.
- **No operational alerting.** Real conjunction warnings (CDMs) and impact-risk assessment
  (Sentry) are explicitly out of scope; we model the *data*, not mission-critical decisions.

---

## Cross-Cutting: UAE Market Relevance

Both sources map onto active UAE space initiatives:

- **Satellites (CelesTrak):** national SSA and space-sustainability regulation under the
  **UAE Space Agency**; orbital monitoring for **MBRSC** assets (KhalifaSat, MBZ-SAT) and
  GEO operators (**Yahsat**, **Thuraya**); UN-registry compliance via `OWNER = UAE` filtering.
- **Asteroids (NASA NeoWs):** directly relevant to the UAE's **MBR Explorer** asteroid-belt
  mission (launch ~2028, landing on Justitia ~2034) and to STEM/outreach goals.

See each source's deep-dive document for detailed UAE use cases.

---

## See Also

- [source_nasa_neo.md](source_nasa_neo.md) — NASA NEO source analysis
- [source_celestrak.md](source_celestrak.md) — CelesTrak source analysis
- [scope.md](scope.md) — platform scope, personas, and objectives
- [ingestion_batch.md](ingestion_batch.md) — how these sources are ingested
- [data_flow.md](data_flow.md) — end-to-end bronze → silver → gold flow
