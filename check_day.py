"""Inspect one line on chosen service days: statuses, poll counts and reason text."""
import sys

import pandas as pd

LINE = sys.argv[1] if len(sys.argv) > 1 else "Elizabeth line"
DAYS = sys.argv[2:] or ["2026-10-25", "2026-11-01"]

df = pd.read_csv("data/processed/line_status.csv", parse_dates=["fetched_at_utc"])
df = df[df["line_name"] == LINE].copy()
local = df["fetched_at_utc"].dt.tz_convert("Europe/London")
df["service_day"] = (local - pd.Timedelta(hours=4)).dt.date.astype(str)

for day in DAYS:
    d = df[df["service_day"] == day]
    print(f"\n=== {LINE}, service day {day} ===")
    if d.empty:
        print("No rows for this day (the line was Service Closed in every poll).")
        continue
    print(f"polls with a status: {d['fetched_at_utc'].nunique()}")
    print(d.groupby(["status_severity", "status_description"]).size().to_string())
    print("\nDistinct reason texts (first 5):")
    print(d["reason"].dropna().drop_duplicates().head(5).to_string())