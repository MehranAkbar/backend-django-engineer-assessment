# Spotter fuel route planner

A Django JSON API, SQLite station database, and small Leaflet map. It finds the minimum fuel purchase cost along one provider-selected route, including estimated station detours. No station is geocoded during an API request.

**Verification status:** implementation and mocked tests are available. This execution environment blocks DNS for dependency downloads and external APIs. The pinned production environment, Census matches and real-world demo routes could not be verified here. See `reports/VALIDATION.md` for exact results and the fallback test environment. Do not present the mocked examples as live routes.

## Setup (Windows PowerShell)

Install Python **3.12.14**. Django is pinned to **6.1.3**, the latest stable release shown by the [official download page](https://www.djangoproject.com/download/) on 18 November 2026. [Django's compatibility table](https://docs.djangoproject.com/en/6.1/faq/install/) supports Python 3.12. The `.python-version` file is also usable with `uv`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Only if .env does not already exist:
Copy-Item .env.example .env
# Put your ORS_API_KEY in .env. Never commit it.
python manage.py migrate
python manage.py prepare_boundary
python manage.py import_stations --pilot --report reports/pilot.json
python manage.py import_stations --geocode --report reports/import.json
# Optional, quota-bounded station venue matching for highway descriptions:
python manage.py geocode_stations --pilot
python manage.py geocode_stations --limit 500
python manage.py test
python manage.py check
python manage.py runserver
```

On macOS/Linux use `python3.12 -m venv .venv` and `source .venv/bin/activate`. If using uv: `uv python install 3.12.14`, `uv venv --python 3.12.14`, then `uv pip install -r requirements.txt`.

Open http://127.0.0.1:8000/ for the map. Import `postman/Spotter.postman_collection.json` into Postman. The collection needs no secret: only the Django server calls ORS. The map's Leaflet CDN and OpenStreetMap tiles require internet access.

## API contract

`POST /api/route-plan/`, `Content-Type: application/json`

```json
{"start":"Chicago, IL","finish":"Milwaukee, WI"}
```

Or coordinates (latitude first in the object; GeoJSON remains longitude first):

```json
{"start":{"latitude":41.8781,"longitude":-87.6298},"finish":{"latitude":43.0389,"longitude":-87.9065}}
```

Mixed input types are supported. Text must include a comma separating city/state or address components. Low-confidence or geographically competing matches are rejected. Coordinates are checked locally against a pinned Natural Earth US polygon, not a rectangular bounding box. The approximate 1:10m boundary can reject coastline/border addresses; territories are outside the intended 50-state/DC scope. No reverse-geocoding call is required. ORS routing avoids international borders.

Success fields: `route` (GeoJSON FeatureCollection), `route_distance_miles`, `fuel_stops`, `estimated_total_distance_miles`, `estimated_gallons_consumed`, `total_fuel_spend_usd`, `assumptions`, `attribution`, and `upstream_calls`. Each stop includes OPIS ID, name, address, coordinates, route mile, price, purchased gallons, USD cost, projected route point and estimated round-trip detour miles. Money is serialized as decimal strings; gallons and miles are numbers.

The vehicle starts with **50 gallons**, uses **10 mpg**, and cannot carry more than 50 gallons. Initial fuel is excluded from spend. A 400-mile route consumes 40 gallons while reporting **$0.00** in new purchases. Purchases are continuous quantities, not compulsory full tanks. No destination purchase is permitted. Each stop cost is rounded half-up to cents from the unrounded quantity; the displayed total is the sum of displayed stop costs. Quantities are displayed to eight decimal places.

Errors use `{"error":{"code":"no_feasible_plan","message":"..."},"upstream_calls":1}`. Statuses: 400 invalid/outside-US/ambiguous input; 415 content type; 422 no route/no feasible fuel plan/provider distance limit; 429 upstream quota; 502 upstream connectivity or malformed response; 503 missing configuration/boundary or optimization limit; 504 upstream timeout. Failed results are not cached. There are no automatic request retries.

## Find the code quickly

| Concern | File |
| --- | --- |
| HTTP validation and response | `planner/views.py` |
| ORS calls, caching and counters | `planner/provider.py` |
| CSV preprocessing and Census batch calls | `planner/management/commands/import_stations.py` |
| Local station-to-segment projection | `planner/geography.py` |
| Independent fuel optimizer | `planner/optimizer.py` |
| Map preview | `templates/map.html` |
| Tests and independent oracle | `planner/tests/` |

## Station preprocessing

The supplied CSV has 8,151 rows and 6,738 distinct OPIS IDs. `Retail Price` is used unchanged as USD/gallon; OPIS IDs are strings. The first valid row for each OPIS ID wins deterministically, including its price. Conflicting duplicate addresses are reported; aliases at the same address do not create extra pumps. Invalid prices, missing required values and invalid US states are rejected. No prices are inferred or refreshed.

Import is transactional and idempotent. A location fingerprint preserves coordinates on unchanged imports and invalidates them when addresses change. Stations absent from a replacement CSV become inactive. Rejected input and unresolved stations are reported separately. No unresolved/inactive station enters optimization.

The pilot submits five numbered street addresses and five highway descriptions to the [US Census batch geocoder](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html). Full geocoding submits only numbered street addresses, in batches of 1,000 (official maximum: 10,000). Census expects ID, street, city, state, ZIP; empty ZIPs are allowed. It requires structure addresses and interpolates positions along address ranges. It is not a reliable resolver for interstate exits, and its matches are not verified pump entrances. The `Public_AR_Current` benchmark can change; reports preserve input hashes, match outcomes and provenance, but rerunning at a later benchmark may produce different coordinates.

Only five retained stations have numbered street addresses. Set `GEOAPIFY_API_KEY` in .env and run `python manage.py geocode_stations --provider geoapify --pilot` to try up to ten unresolved stations. Geoapify searches the station name and locality for highway descriptions and the supplied address for numbered streets. A single matching fuel venue or matching building address can enter routing. Review other candidates in `reports/geoapify-stations.json`. Use `--limit 100` for a larger batch, or `--retry-unmatched` to include prior Geoapify misses. One sequential run uses one request per station and pauses on any provider error. Run one batch at a time within the account's daily quota. Previously matched stations are preserved. The command defaults to Geoapify when its key is set; `--provider ors` selects the existing ORS matcher.

Highway descriptions remain unresolved unless a geocoder passes these quality gates or a coordinate is independently verified. Import manual corrections with:

```powershell
python manage.py import_stations --coordinates verified-stations.csv
```

The override CSV needs `opis_id,latitude,longitude,source`. Do not substitute city centroids. Use a traceable station/operator or geographic source and record its URL/date. A missing US boundary must be resolved before accepting coordinates. Reports contain coverage, rejection reasons and an unresolved CSV. Because `.sqlite3` is ignored, reviewers must reproduce preprocessing or use an explicitly reviewed coordinate export; the repository contains no invented station locations. After successful geocoding, `python manage.py dumpdata planner.Station --indent 2 --output data/stations.json` captures the station dataset and its provenance for reproducibility; `python manage.py loaddata data/stations.json` restores it. Review provider/data licensing before sharing that snapshot.

## Route matching and distance model

For every usable station, NumPy projects onto **segments** of the returned road geometry, including points between vertices. The nearest projection gives route chainage; cumulative great-circle geometry lengths are scaled to ORS's reported route distance. A local equirectangular segment projection is an approximation, suitable for ordinary road segments. Repeated/looped routes use the nearest occurrence only; antimeridian routes are unsupported.

The default corridor is **1 mile** perpendicular to the route (`CORRIDOR_MILES`). One-way access distance is `perpendicular_miles × DETOUR_FACTOR` (default 1.5). Each selected stop adds an out-and-back detour, so travel from station i to j is:

`route_mile[j] - route_mile[i] + one_way_detour[i] + one_way_detour[j]`

Both legs consume fuel. Orange dashed connectors on the map show these estimates. They are **not routed access roads**: barriers, divided highways, exits and pump entrances may invalidate them. Directions returns the main route only; it is not regenerated through stations, preserving the one-call budget. The profile is `driving-car`; truck height/weight restrictions are not modeled. The assignment's range/mpg assumptions alone do not define an HGV profile.

## Why the optimizer works

Each eligible station is a node in increasing route-mile order, plus start and finish. An arc exists only when travel under the distance model is at most 500 miles. A binary flow chooses one forward path. A continuous variable on each selected arc is fuel leaving its origin; it must cover that leg and cannot exceed 50 gallons. At each station, outgoing fuel equals incoming fuel minus consumption plus purchased gallons. The start supplies exactly 50 gallons; the destination can retain fuel but cannot buy any.

Minimize `sum(price × gallons_purchased)` using SciPy's HiGHS mixed-integer solver. Every modeled feasible itinerary has a feasible solution in these constraints and vice versa; minimizing this objective therefore minimizes fuel purchase cost over the entire modeled itinerary. Unlike choosing the cheapest nearby station, the solver must also reach the destination. Tests compare small instances against independently enumerated paths and fixed-path greedy fuel purchasing.

Optimality covers the provider-selected route, accepted station set, one occurrence per station, forward travel and estimated detours. It does not cover alternative roads, backtracking, real station access or updated prices. Floating-point tolerances apply. The solver must prove optimality (`mip_rel_gap=0`); it returns an explicit error on a 20-second limit rather than claiming an unproven plan is optimal. More than 250 candidates returns `too_many_candidates`; no silent candidate pruning changes the claimed optimum. Reduce the corridor when appropriate. MILP has worst-case exponential complexity, so this cap is an explicit local-demo limitation.

## ORS evaluation, quotas, caching and attribution

Verified official references on 18 November 2026:

- [Directions contract](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/requests-and-return-types): POST GeoJSON; coordinates in longitude/latitude; summary distance in meters.
- [Host migration](https://ask.openrouteservice.org/t/deprecating-api-openrouteservice-org-in-favour-of-api-heigit-org/7912/): Directions now uses `https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson`; geocoding uses `https://api.heigit.org/pelias/v1/search`. The existing key works with the new host.
- [Hosted restrictions](https://giscience.github.io/openrouteservice/hosted-api-restrictions): driving distance up to 6,000 km. Routes beyond this limit need a self-hosted provider or a different plan/architecture; this implementation does not split them into multiple Directions requests.
- [Official published Standard plan](https://staging.openrouteservice.org/plans/): Directions 2,000/day and 40/minute; geocoding 1,000/day and 100/minute. The [current account page](https://account.heigit.org/info/plans) is client-rendered and could not be read by the research tool, so verify the effective quota in your key dashboard. Do not treat older published limits as an account-specific guarantee.
- [Provider licensing clarification](https://ask.openrouteservice.org/t/free-plan-in-an-app-with-a-paid-tier-license-cc-by-sa-4-0-personal-data-and-attribution-questions/8079/): results licensed CC BY-SA 4.0. [Current terms](https://account.heigit.org/info/tos) and [published attribution](https://staging.openrouteservice.org/terms-of-service/) should be reviewed before hosting or redistributing outputs.

Coordinate requests make one Directions request on a cold cache. Text requests make at most two geocodes and one Directions request. Normalization collapses whitespace and lowercases text. Both successful geocodes and routes have a one-hour in-process cache, with source attribution preserved; this is local reuse of licensed results, not bulk prefetching. `CACHE_TTL=0` disables retention if your applicable provider terms require it. Multiple processes have separate caches. No persistent user location history is stored. Logs contain only elapsed time and upstream counts, never keys or addresses. The initial station import uses Census, not the ORS daily geocoding quota.

Map and API display attribution to ORS/HeiGIT and OpenStreetMap. Redistributed routing results retain CC BY-SA 4.0 attribution; this does not assert a license over the supplied proprietary fuel CSV. Natural Earth boundary data is public domain, pinned to v5.1.2, with source URL and download SHA recorded by `prepare_boundary`. OpenStreetMap tiles follow normal browser loading: no bulk downloads or offline tile cache.

## Demo and measurements

```powershell
python manage.py smoke_routes
```

This uses imported stations and real ORS calls for Chicago–Milwaukee (short) and Salt Lake City–Chicago (intended multi-stop). It clears the cache before each cold request and repeats it warm. Actual responses and environment/timings go in `reports/live/`. A route is only marked verified if it succeeds, and the multi-stop case must return at least two fuel stops. If matched coverage cannot bridge the route, the failure remains recorded; choose another route or improve coordinates, never fabricate matches.

`python scripts/generate_demo.py` produces clearly marked **mocked** short/multi-stop examples and timings in `examples/`, using an isolated temporary database. Geometry, distances, stations and boundary checks are synthetic. These demonstrate the schema, map rendering and optimizer only. `docs/LOOM.md` is a 4:45 recording outline. Live verification remains required before submitting.

## Sharing and limitations

The project is intended for local assessment: no authentication, public hosting, production hardening or concurrency guarantees. The unauthenticated endpoint is CSRF-exempt for Postman; do not expose it directly on the internet. Keep `.env`, virtual environments and SQLite out of Git. Run `git diff --check`, tests, Django checks and live smoke checks before sharing. Publishing and submission are deliberately left to you.
