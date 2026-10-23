import pandas as pd

df = pd.read_csv("data/processed/line_status.csv", parse_dates=["fetched_at_utc"])

polls = pd.Series(sorted(df["fetched_at_utc"].unique()))
gaps = polls.diff().dt.total_seconds() / 60

print(f"Polls: {len(polls)}  first: {polls.min()}  last: {polls.max()}")
print(f"Median gap between polls (min): {gaps.median():.1f}")
print(f"Gaps longer than 10 min: {(gaps > 10).sum()}")

lines_per_poll = df.groupby("fetched_at_utc")["line_id"].nunique()
print(f"Lines per poll, min / max: {lines_per_poll.min()} / {lines_per_poll.max()}")

print("Severity codes seen:", sorted(int(x) for x in df["status_severity"].dropna().unique()))
print("\nStatus counts:")
print(df["status_description"].value_counts(dropna=False))
print("Days covered:", df["fetched_at_utc"].dt.date.nunique())