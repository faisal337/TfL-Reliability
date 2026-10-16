import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.tfl.gov.uk"
MODES = os.getenv("TFL_MODES", "tube,overground,dlr,elizabeth-line")
APP_KEY = os.getenv("TFL_APP_KEY", "")
RAW_DIR = Path("data/raw")
INTERVAL_SECONDS = 300  # 5 minutes
TIMEOUT_SECONDS = 10


def fetch_status() -> list[dict]:
    """Call the TfL Line Status endpoint and return the parsed JSON."""
    url = f"{BASE_URL}/Line/Mode/{MODES}/Status"
    params = {"app_key": APP_KEY} if APP_KEY else {}
    response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def save_snapshot(lines: list[dict], fetched_at: datetime) -> Path:
    """Write one snapshot to data/raw/YYYY-MM-DD/HHMMSS.json (UTC)."""
    day_dir = RAW_DIR / fetched_at.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{fetched_at.strftime('%H%M%S')}.json"
    record = {"fetched_at_utc": fetched_at.isoformat(), "lines": lines}
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def run_once() -> None:
    fetched_at = datetime.now(timezone.utc)
    try:
        lines = fetch_status()
    except requests.RequestException as exc:
        # Log and carry on: a failed poll should not stop the collector.
        print(f"[{fetched_at:%H:%M:%S}] fetch failed: {exc}")
        return
    path = save_snapshot(lines, fetched_at)
    print(f"[{fetched_at:%H:%M:%S}] saved {len(lines)} lines -> {path}")


def main() -> None:
    print(f"Polling modes [{MODES}] every {INTERVAL_SECONDS}s. Ctrl+C to stop.")
    while True:
        started = time.monotonic()
        run_once()
        elapsed = time.monotonic() - started
        time.sleep(max(0, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    try:
        if "--once" in sys.argv:
            run_once()  # single test poll
        else:
            main()
    except KeyboardInterrupt:
        print("Stopped.")