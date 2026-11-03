import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
ssm = boto3.client("ssm")

BUCKET = os.environ["BUCKET"]
STATIONS_KEY = os.environ.get("STATIONS_KEY", "reference/tube_stations.json")
KEY_PARAM = os.environ.get("TFL_KEY_PARAM", "")
USER_AGENT = "tfl-reliability-poller/1.0 (learning project)"
WORKERS = 2          # with the 0.15s pause below, roughly 350 requests a minute, under the 500 limit
PAUSE_SECONDS = 0.5


def load_app_key() -> str:
    if not KEY_PARAM:
        return ""
    return ssm.get_parameter(Name=KEY_PARAM, WithDecryption=True)["Parameter"]["Value"]


APP_KEY = load_app_key()


def load_stations() -> list[dict]:
    obj = s3.get_object(Bucket=BUCKET, Key=STATIONS_KEY)
    return json.loads(obj["Body"].read())


def fetch(naptan: str) -> dict:
    url = f"https://api.tfl.gov.uk/crowding/{naptan}/Live"
    if APP_KEY:
        url += "?" + urllib.parse.urlencode({"app_key": APP_KEY})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})

    last_error = ""
    for attempt in range(3):
        time.sleep(PAUSE_SECONDS * (attempt + 1))
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return {"naptan": naptan, "ok": True, "body": json.loads(r.read())}
        except urllib.error.HTTPError as exc:
            last_error = str(exc)[:200]
            if exc.code != 429:
                break  # other HTTP errors won't succeed on retry
        except Exception as exc:
            last_error = str(exc)[:200]
    return {"naptan": naptan, "ok": False, "error": last_error}


def lambda_handler(event, context):
    fetched_at = datetime.now(timezone.utc)
    stations = load_stations()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(fetch, [s["naptan"] for s in stations]))

    failed = sum(not r["ok"] for r in results)
    body = {
        "fetched_at_utc": fetched_at.isoformat(),
        "station_count": len(results),
        "failed": failed,
        "stations": results,
    }
    key = f"raw/crowding/{fetched_at:%Y-%m-%d}/{fetched_at:%H%M%S}.json.gz"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=gzip.compress(json.dumps(body).encode("utf-8")),
        ContentType="application/gzip",
    )
    return {"status": "ok", "stations": len(results), "failed": failed, "key": key}