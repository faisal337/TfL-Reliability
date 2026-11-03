"""Load data/processed/line_status.csv into DuckDB for dbt."""
from pathlib import Path

import duckdb

CSV = Path("data/processed/line_status.csv")
DB = Path("data/tfl.duckdb")


def main() -> None:
    if not CSV.exists():
        raise FileNotFoundError(f"{CSV} not found. Run flatten.py first.")
    con = duckdb.connect(str(DB))
    con.execute(
        f"create or replace table line_status_raw as "
        f"select * from read_csv_auto('{CSV.as_posix()}')"
    )
    rows = con.execute("select count(*) from line_status_raw").fetchone()[0]
    con.close()
    print(f"Loaded {rows} rows into line_status_raw")


if __name__ == "__main__":
    main()