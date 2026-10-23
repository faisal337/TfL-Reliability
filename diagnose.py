import pandas as pd

df = pd.read_csv("data/processed/line_status.csv", parse_dates=["fetched_at_utc"])
df["local"] = df["fetched_at_utc"].dt.tz_convert("Europe/London")
df["hour"] = df["local"].dt.hour

# Non-good statuses between 01:00 and 03:59 local time, excluding code 20 (already removed from metrics)
night = df[
    df["hour"].between(1, 3)
    & ~df["status_severity"].isin([10, 20])
]

print("Piccadilly, overnight non-good statuses by weekday:")
pic = night[night["line_name"] == "Piccadilly"]
print(pic.groupby([pic["local"].dt.day_name(), "status_description"]).size().unstack(fill_value=0))

print("\nAll lines, overnight non-good statuses:")
print(night.groupby(["line_name", "status_description"]).size().unstack(fill_value=0))