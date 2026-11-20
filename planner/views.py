import json
import logging
import time
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .errors import PlanError
from .geography import nearby_stations
from .models import Station
from .optimizer import optimize
from .provider import ORSClient

logger = logging.getLogger("planner")


@csrf_exempt
def route_plan(request):
    client = ORSClient()
    started = time.perf_counter()
    try:
        if request.method != "POST":
            raise PlanError("method_not_allowed", "Use POST.", 405)
        if request.content_type != "application/json":
            raise PlanError("invalid_content_type", "Use application/json.", 415)
        if len(request.body) > 10000:
            raise PlanError("payload_too_large", "Request is too large.", 413)
        try:
            body = json.loads(request.body)
        except (ValueError, UnicodeError):
            raise PlanError("invalid_json", "Request must contain valid JSON.", 400)
        if not isinstance(body, dict) or set(body) != {"start", "finish"}:
            raise PlanError("invalid_input", "Provide exactly start and finish.", 400)

        start = client.endpoint(body["start"])
        finish = client.endpoint(body["finish"])
        if start == finish:
            raise PlanError(
                "identical_endpoints", "Start and finish must differ.", 400
            )

        route = client.route(start, finish)
        feature = route["features"][0]
        distance = feature["properties"]["summary"]["distance"] / 1609.344

        candidates, details = [], {}
        if distance > 500:
            candidates, details = nearby_stations(
                feature["geometry"]["coordinates"],
                distance,
                Station.objects.filter(status="matched"),
                settings.CORRIDOR_MILES,
                settings.DETOUR_FACTOR,
            )

        purchases, traveled = optimize(distance, candidates)
        stops = []
        total = Decimal("0.00")
        for stop, gallons in purchases:
            station, projection = details[stop.id]
            cost = (
                Decimal(str(gallons)) * station.price
            ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            total += cost
            stops.append(
                {
                    "opis_id": station.opis_id,
                    "station_name": station.name,
                    "address": (
                        station.verified_address
                        or f"{station.address}, {station.city}, {station.state}"
                    ),
                    "coordinates": {
                        "latitude": station.latitude,
                        "longitude": station.longitude,
                    },
                    "route_mile": round(stop.mile, 3),
                    "route_projection": projection,
                    "price_per_gallon": str(station.price),
                    "gallons_purchased": round(gallons, 8),
                    "stop_cost": str(cost),
                    "estimated_round_trip_detour_miles": round(stop.detour * 2, 4),
                }
            )

        result = {
            "route": route,
            "route_distance_miles": round(distance, 3),
            "fuel_stops": stops,
            "estimated_total_distance_miles": round(traveled, 3),
            "estimated_gallons_consumed": round(traveled / 10, 8),
            "total_fuel_spend_usd": str(total),
            "assumptions": {
                "initial_fuel_gallons": 50,
                "tank_capacity_gallons": 50,
                "miles_per_gallon": 10,
                "spend": "Purchases after departure only; initial full tank is excluded.",
                "optimality": (
                    "Minimum purchase cost on this route, eligible stations and "
                    "estimated detour model; not a globally cheapest road route."
                ),
                "detours": (
                    "Estimated out-and-back: 2 × perpendicular distance × "
                    f"{settings.DETOUR_FACTOR}. Not road-routed; access is not "
                    "verified."
                ),
                "corridor_miles": settings.CORRIDOR_MILES,
            },
            "attribution": (
                "© openrouteservice.org by HeiGIT | Map data © OpenStreetMap "
                "contributors; routing results CC BY-SA 4.0"
            ),
            "upstream_calls": client.calls,
        }
        return JsonResponse(result)
    except PlanError as error:
        return JsonResponse(
            {
                "error": {"code": error.code, "message": error.message},
                "upstream_calls": client.calls,
            },
            status=error.status,
        )
    finally:
        logger.info(
            "route_plan upstream_calls=%s elapsed_ms=%.2f",
            client.calls,
            (time.perf_counter() - started) * 1000,
        )
