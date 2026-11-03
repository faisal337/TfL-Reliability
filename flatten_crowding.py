"""Flatten crowding snapshots into one row per station per poll."""
import gzip
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/crowding")
STATIONS_FILE = Path("reference/tube_stations.json")
OUT_FILE = Path("data/processed/crowding_readings.csv")


def load_station_names() -> dict[str, str]:
    if not STATIONS_FILE.exists():
        return {}
    return {s["naptan"]: s["name"] for s in json.loads(STATIONS_FILE.read_text(encoding="utf-8"))}


def iter_rows(names: dict[str, str]):
    for path in sorted(RAW_DIR.glob("*/*.json.gz")):
        record = json.loads(gzip.decompress(path.read_bytes()))
        poll = record["fetched_at_utc"]
        for s in record.get("stations", []):
            body = s.get("body") or {}
            yield {
                "poll_utc": poll,
                "station_naptan": s.get("naptan"),
                "station_name": names.get(s.get("naptan")),
                "fetch_ok": bool(s.get("ok")),
                "error": s.get("error"),
                "data_available": body.get("dataAvailable"),
                "pct_of_baseline": body.get("percentageOfBaseline"),
                "reading_utc": body.get("timeUtc"),
                "reading_local": body.get("timeLocal"),
                "source_file": str(path),
            }


def main() -> None:
    if not RAW_DIR.exists():
        print(f"{RAW_DIR} not found. Run sync_s3.py first.")
        return

    names = load_station_names()
    df = pd.DataFrame(list(iter_rows(names)))
    if df.empty:
        print("No crowding snapshots found.")
        return

    df["poll_utc"] = pd.to_datetime(df["poll_utc"], utc=True)
    df["reading_utc"] = pd.to_datetime(df["reading_utc"], utc=True, errors="coerce")
    df["lag_min"] = (df["poll_utc"] - df["reading_utc"]).dt.total_seconds() / 60
    df = df.drop_duplicates(subset=["poll_utc", "station_naptan"])

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False)

    ok = df[df["fetch_ok"]]
    avail = ok[ok["data_available"] == True]  # noqa: E712
    print(f"Rows: {len(df)}  polls: {df['poll_utc'].nunique()}  stations: {df['station_naptan'].nunique()}")
    print(f"Fetch failures: {(~df['fetch_ok']).sum()}")
    print(f"Data available: {len(avail)} of {len(ok)} successful rows")
    print(f"pct_of_baseline min / median / max: "
          f"{avail['pct_of_baseline'].min():.3f} / {avail['pct_of_baseline'].median():.3f} / {avail['pct_of_baseline'].max():.3f}")
    print(f"Readings above 1.0: {(avail['pct_of_baseline'] > 1).sum()}")
    print(f"Reading lag, minutes (median / max): {df['lag_min'].median():.1f} / {df['lag_min'].max():.1f}")
    print(f"\nWrote {OUT_FILE}")


if __name__ == "__main__":
    main()