import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
ssm = boto3.client("ssm")

BUCKET = os.environ["BUCKET"]
MODES = os.environ.get("TFL_MODES", "tube,overground,dlr,elizabeth-line")
KEY_PARAM = os.environ.get("TFL_KEY_PARAM", "")
USER_AGENT = "tfl-reliability-poller/1.0 (learning project)"


def load_app_key() -> str:
    """Read the TfL key from SSM at cold start. Empty string if not configured."""
    if not KEY_PARAM:
        return ""
    param = ssm.get_parameter(Name=KEY_PARAM, WithDecryption=True)
    return param["Parameter"]["Value"]


APP_KEY = load_app_key()


def lambda_handler(event, context):
    fetched_at = datetime.now(timezone.utc)

    params = {"app_key": APP_KEY} if APP_KEY else {}
    url = f"https://api.tfl.gov.uk/Line/Mode/{MODES}/Status"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        lines = json.loads(response.read())

    key = f"raw/{fetched_at:%Y-%m-%d}/{fetched_at:%H%M%S}.json"
    body = json.dumps({"fetched_at_utc": fetched_at.isoformat(), "lines": lines})
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )
    return {"status": "ok", "lines": len(lines), "key": key}