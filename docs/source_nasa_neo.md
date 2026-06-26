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
