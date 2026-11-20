# Validation — 18 November 2026

## Status

The implementation is present, but **not ready to claim a fully live-verified submission**. Network DNS restrictions blocked PyPI, GitHub boundary downloads, Census and ORS. An ORS key was already configured and was not printed or committed. No station coordinates or successful live responses were fabricated.

## Environments

- Deliverable pins: Python **3.12.14**, Django **6.1.3**, SciPy **1.17.1**, NumPy **2.4.6**, Requests **2.34.2**, python-dotenv **1.2.4**.
- Actual fallback execution: Windows 10 build 26300, Python **3.11.9**, Django **4.2.1**, SciPy **1.17.1**, NumPy **2.4.6**. The latter two were recovered from existing local cached wheels into an isolated ignored test environment. This is diagnostic evidence, **not verification of Django 6.1.3**.
- Latest Django release and supported Python series were verified using official documentation; installing the target dependency set failed at DNS resolution.

## Automated and static checks

- Tests cover full-tank short/exact-range trips, multiple stops, partial fills, cheapest-first failure, lookahead, detour feasibility/cost, unreachable gaps, no destination purchase, and 12 seeded comparisons with an independent exhaustive-path oracle.
- API tests mock providers and verify coordinate/text call budgets, normalized warm caches, errors, malformed geometry, stop-cost reconciliation and unresolved-station exclusion.
- Import tests cover duplicate/rejected rows, idempotency, preserved matches and mocked Census output. ORS station-quality tests reject city centroids, unrelated venues and highway address guesses.
- **35 automated tests passed** on the fallback environment described above. Final output: `reports/tests.txt`.
- Django system checks: no issues. Migration drift check: no changes detected (fallback environment).
- Python compilation and `git diff --check`: passed.
- Target-environment Django check could not start because Django installation was blocked. It is not reported as passed.
- HTML was served in Django's test client; interactive browser/tile rendering was not live-verified.

## Import observations

| Measure | Result |
| --- | ---: |
| Source rows | 8,151 |
| Distinct OPIS IDs in source, including non-US | 6,738 |
| Rejected rows (non-US province codes) | 620 |
| Duplicate valid US rows | 905 |
| Unique retained US stations | 6,626 |
| Conventional numbered street addresses | 5 |
| Accepted coordinates | 0 |
| Unresolved retained stations | 6,626 |
| Coverage | 0% |

`reports/pilot.json` records ten selected inputs: five streets and five highway/other descriptions. One Census batch call was attempted and failed to connect. `reports/import.json` records the full import and attempted Census batch for all five eligible numbered streets; it also failed. The input SHA256 is preserved in both reports. The full dataset was imported into local SQLite, but no coordinates were accepted.

Census cannot cover most of this file because it expects structure addresses. The optional ORS station preprocessing command provides conservative venue matching under an explicit call budget. That fallback could not run live without the boundary download. Manual verified overrides are also supported. Useful national coverage within a three-day Standard-plan quota is not guaranteed.

## Live attempts

`reports/provider-probe.json`: one real ORS Directions attempt, failed with `provider_unavailable` in **0.022785 seconds**. This measures a connection failure, not routing performance.

`reports/live/timings.json`: attempted Chicago–Milwaukee and Salt Lake City–Chicago through the API. All returned **503 boundary_missing**, zero upstream calls, and `verified_for_demo: false`. Their recorded response times are failure-path timings and must not be used as live performance claims.

No verified short route or verified multi-stop route is available yet. Run `prepare_boundary`, geocoding, and `smoke_routes` on a network-enabled machine to replace these failed observations.

## Mocked measurements only

Measured through Django's test client with mocked Directions, mocked boundary validation and synthetic stations in a temporary database. These are not measurements with imported geocoded fuel data or network latency.

| Synthetic route | Cold | Warm | Upstream mock calls cold/warm | Stops |
| --- | ---: | ---: | --- | ---: |
| 100 miles, (-110, 40) → (-108, 40) | 1.954031 s | 0.001439 s | 1 / 0 | 0 |
| 1,400 miles, (-110, 40) → (-96, 40) | 0.050522 s | 0.007987 s | 1 / 0 | 3 |

The first request includes module-import/startup overhead, so its cold/warm difference is not solely a cache effect. Repeating measurements after imports will differ. Exact mock responses and machine metadata are in `examples/`.

## Remaining work before submission

1. Install `requirements.txt` under Python 3.12.14 and rerun tests/checks.
2. Download the pinned US boundary; run the Census/ORS pilots with real access and inspect accepted matches.
3. Improve station coverage using bounded ORS batches and independently verified coordinates. Keep ambiguous records unresolved.
4. Run `smoke_routes`; retain a successful short route and a successful route with at least two stops, plus their live cold/warm timings.
5. Inspect the map in a browser, import the Postman collection and record the 4:45 Loom outline.

Known modeling limits: one route, approximate station detours, no truck-size restrictions, outdated input prices, nearest route occurrence only, no backward travel, at most 250 eligible candidates and a 20-second solver limit. No deployment or submission was performed.
