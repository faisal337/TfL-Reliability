"""Build reference/tube_stations.json: every Underground station, from TfL's Line StopPoints endpoint."""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

APP_KEY = os.getenv("TFL_APP_KEY", "")
UA = "tfl-reliability-poller/1.0 (learning project)"
TUBE_LINES = [
    "bakerloo", "central", "circle", "district", "hammersmith-city", "jubilee",
    "metropolitan", "northern", "piccadilly", "victoria", "waterloo-city",
]
OUT = Path("reference/tube_stations.json")


def get(path: str):
    params = {"app_key": APP_KEY} if APP_KEY else {}
    url = f"https://api.tfl.gov.uk{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main() -> None:
    stations = {}
    for line in TUBE_LINES:
        for sp in get(f"/Line/{line}/StopPoints"):
            naptan = sp.get("id", "")
            # Keep only Underground stations (940GZZLU...), and only the station record
            # itself, not platforms or entrances under it.
            if naptan.startswith("940GZZLU") and sp.get("stopType") == "NaptanMetroStation":
                stations[naptan] = {"naptan": naptan, "name": sp.get("commonName")}
        time.sleep(0.5)  # stay well inside the rate limit

    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = sorted(stations.values(), key=lambda s: s["name"] or "")
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {len(result)} stations to {OUT}")


if __name__ == "__main__":
    main()