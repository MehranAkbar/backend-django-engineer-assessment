# Loom outline — 4 minutes 45 seconds

Before recording, run setup/import/tests and `python manage.py smoke_routes`. Use only routes marked `verified_for_demo: true` in `reports/live/timings.json`. Current examples are mocked because this build environment cannot reach providers. Do not call them live verified routes.

| Time | Screen and narration |
| --- | --- |
| 0:00–0:25 | State the goal: choose cost-effective fuel purchases on a US route. Full 50-gallon tank, 10 mpg, initial fuel excluded from spend. |
| 0:25–1:00 | Postman: short route. Show distance, gallons consumed, no stops and $0 new purchases. |
| 1:00–1:45 | Postman: verified multi-stop route. Show ordered OPIS IDs, retail prices, partial gallons, per-stop costs and reconciled total. |
| 1:45–2:20 | Browser map: route and fuel markers. Paste the exact Postman JSON into Render a Postman response. Open a marker. Explain orange connectors are estimated detours, not road-routed access. |
| 2:20–3:15 | Open `planner/optimizer.py`. Explain forward path selection, fuel conservation, 50-gallon capacity and total purchase-cost objective. Cheap nearby fuel is only useful if the rest of the trip is feasible. Show lookahead and detour tests. |
| 3:15–3:55 | Open import report and command. CSV processed once; duplicates handled by OPIS, Census street matches persisted, unresolved highway addresses excluded. Zero station geocoding in requests. |
| 3:55–4:25 | Show measured live cold/warm results and upstream counts. Coordinates: 1 cold call, 0 warm; text: at most 3. Mention local cache scope. |
| 4:25–4:45 | Show passing tests and README. State limitations: one chosen route, approximate station access, incomplete coverage, stale CSV prices and solver limits. End with local setup commands. |

Interview answer: “I modeled fuel as inventory flowing along a forward path. Every leg must have enough fuel, every tank has a capacity, and purchases cost the station's price. The optimizer considers the whole trip. Preprocessing resolves station coordinates once, so live requests only geocode the two user inputs if needed and fetch one route.”
