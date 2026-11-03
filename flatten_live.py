"""Flatten live TfL responses into one row per record. Used by the Lambdas and for local tests."""
import hashlib


def flatten_arrivals(body: list, fetched_at: str) -> list[dict]:
    rows = []
    for p in body:
        rows.append({
            "fetched_at_utc": fetched_at,
            "prediction_id": str(p.get("id")),
            "station_naptan": p.get("naptanId"),
            "station_name": p.get("stationName"),
            "line_id": p.get("lineId"),
            "line_name": p.get("lineName"),
            "mode": p.get("modeName"),
            "platform": p.get("platformName"),
            "direction": p.get("direction"),
            "towards": p.get("towards"),
            "destination_naptan": p.get("destinationNaptanId"),
            "time_to_station_sec": p.get("timeToStation"),
            "expected_arrival_utc": p.get("expectedArrival"),
            "current_location": p.get("currentLocation"),
            "vehicle_id": p.get("vehicleId"),
        })
    return rows


def flatten_disruptions(body: list, fetched_at: str) -> list[dict]:
    seen, rows = set(), []
    for d in body:
        text = (d.get("description") or "").strip()
        key = hashlib.md5(text.encode("utf-8")).hexdigest()  # routeInfo and routeBlocking repeat the same text
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "fetched_at_utc": fetched_at,
            "category": d.get("category"),
            "disruption_type": d.get("type"),
            "description": text,
            "description_hash": key,
        })
    return rows


def flatten_bikepoints(places: list, fetched_at: str) -> list[dict]:
    rows = []
    for place in places:
        extras = place.get("additionalProperties", [])
        props = {a["key"]: a["value"] for a in extras}
        modified = next((a.get("modified") for a in extras if a["key"] == "NbBikes"), None)

        def count(key: str) -> int:
            try:
                return int(props.get(key) or 0)
            except ValueError:
                return 0

        docks, bikes, empty = count("NbDocks"), count("NbBikes"), count("NbEmptyDocks")
        rows.append({
            "fetched_at_utc": fetched_at,
            "bikepoint_id": place.get("id"),
            "name": place.get("commonName"),
            "lat": place.get("lat"),
            "lon": place.get("lon"),
            "installed": props.get("Installed") == "true",
            "locked": props.get("Locked") == "true",
            "docks": docks,
            "bikes": bikes,
            "empty_docks": empty,
            "broken_docks": max(docks - bikes - empty, 0),
            "e_bikes": count("NbEBikes"),
            "source_modified_utc": modified,
        })
    return rows