import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")
OUT_FILE = OUT_DIR / "line_status.csv"

def iter_rows():
    """Yield one dict per line per status per snapshot."""
    for path in sorted(RAW_DIR.glob("*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = record["fetched_at_utc"]
        for line in record["lines"]:
            for status in line.get("lineStatuses", []):
                yield {
                    "fetched_at_utc": fetched_at,
                    "line_id": line.get("id"),
                    "line_name": line.get("name"),
                    "mode": line.get("modeName"),
                    "status_severity": status.get("statusSeverity"),
                    "status_description": status.get("statusSeverityDescription"),
                    "reason": status.get("reason"),
                    "num_disruptions": len(line.get("disruptions", [])),
                    "source_file": str(path),
                }


def main() -> None:
    rows = list(iter_rows())
    if not rows:
        print("No snapshots found in data/raw. Run poll.py first.")
        return

    df = pd.DataFrame(rows)
    df["fetched_at_utc"] = pd.to_datetime(df["fetched_at_utc"], utc=True)
    df["is_good_service"] = df["status_severity"] == 10
    df["has_reason"] = df["reason"].notna()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False)

    print(f"Wrote {len(df)} rows to {OUT_FILE}")
    print(f"Snapshots: {df['source_file'].nunique()}")
    print(f"Lines: {df['line_id'].nunique()}")
    print("\nStatus counts:")
    print(df["status_description"].value_counts())


if __name__ == "__main__":
    main()