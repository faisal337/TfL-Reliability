"""Reliability metrics per TfL line, built from data/processed/line_status.csv."""
from pathlib import Path

import pandas as pd

IN_FILE = Path("data/processed/line_status.csv")
OUT_DIR = Path("data/processed")
GOOD_SEVERITY = 10                       # 10 = Good Service in the data seen so far
EPISODE_GAP = pd.Timedelta(minutes=10)   # a larger gap between polls starts a new episode
POLL_MINUTES = 5                         # nominal poll interval, used to estimate episode length
LOCAL_TZ = "Europe/London"


NOT_OPERATING = {20}  # Service Closed: the line is not scheduled to run
SEVERITY_RANK = {10: 0, 9: 1, 7: 2, 5: 3, 4: 3, 6: 4, 3: 4, 2: 5}  # higher = worse
RELIABLE_CODES = {10, 4, 5}  # Good Service, Planned Closure, Part Closure
SERVICE_DAY_CUTOFF_HOURS = 4  # times before 04:00 belong to the previous service day
MIN_BUCKET_POLLS = 20         # ignore hour/weekday buckets with fewer polls than this

def load_per_poll() -> pd.DataFrame:
    """One row per line per poll, using the worst status and a reliability flag."""
    df = pd.read_csv(IN_FILE)
    df["fetched_at_utc"] = pd.to_datetime(df["fetched_at_utc"], utc=True)
    df = df.dropna(subset=["status_severity"])
    df["status_severity"] = df["status_severity"].astype(int)
    df = df[~df["status_severity"].isin(NOT_OPERATING)]

    unknown = set(df["status_severity"]) - set(SEVERITY_RANK)
    if unknown:
        raise ValueError(f"Unmapped severity codes: {unknown}. Add them to SEVERITY_RANK.")

    # A poll is reliable only if every status the line reports is in RELIABLE_CODES.
    reliable = (
        df.assign(ok=df["status_severity"].isin(RELIABLE_CODES))
        .groupby(["fetched_at_utc", "line_id"])["ok"]
        .all()
        .rename("is_reliable")
        .reset_index()
    )

    df["rank"] = df["status_severity"].map(SEVERITY_RANK)
    worst_idx = df.groupby(["fetched_at_utc", "line_id"])["rank"].idxmax()
    per_poll = df.loc[worst_idx].copy()
    per_poll = per_poll.merge(reliable, on=["fetched_at_utc", "line_id"], how="left")

    local = per_poll["fetched_at_utc"].dt.tz_convert(LOCAL_TZ)
    service_day = local - pd.Timedelta(hours=SERVICE_DAY_CUTOFF_HOURS)
    per_poll["is_good"] = per_poll["status_severity"] == GOOD_SEVERITY
    per_poll["date"] = service_day.dt.date
    per_poll["hour"] = local.dt.hour
    per_poll["weekday"] = service_day.dt.day_name()

    return per_poll.sort_values(["line_id", "fetched_at_utc"]).reset_index(drop=True)


def find_episodes(per_poll: pd.DataFrame) -> pd.DataFrame:
    """A disruption episode is a run of consecutive non-good polls on the same line."""
    g = per_poll.copy()
    g["prev_good"] = g.groupby("line_id")["is_reliable"].shift(fill_value=True).astype(bool)
    gap = g.groupby("line_id")["fetched_at_utc"].diff()
    g["new_episode"] = ~g["is_reliable"] & (g["prev_good"] | (gap > EPISODE_GAP))
    g["episode_id"] = g["new_episode"].cumsum()

    bad = g[~g["is_reliable"]]
    episodes = bad.groupby("episode_id").agg(
        line_id=("line_id", "first"),
        line_name=("line_name", "first"),
        mode=("mode", "first"),
        start_utc=("fetched_at_utc", "min"),
        end_utc=("fetched_at_utc", "max"),
        polls=("is_good", "size"),
        worst_rank=("rank", "max"),
    ).reset_index()

    episodes["duration_min"] = (
        (episodes["end_utc"] - episodes["start_utc"]).dt.total_seconds() / 60 + POLL_MINUTES
    ).round(1)

    worst_status = bad.loc[
        bad.groupby("episode_id")["rank"].idxmax(),
        ["episode_id", "status_description"],
    ].rename(columns={"status_description": "worst_status"})

    return episodes.merge(worst_status, on="episode_id").drop(columns="episode_id")


def disruption_rate(per_poll: pd.DataFrame, by: str) -> pd.DataFrame:
    """For each line, the hour or weekday with the highest disrupted share.

    Returns NaN when a line had no disruption, or when no bucket has enough polls.
    """
    rates = (
        per_poll.groupby(["line_id", by])["is_reliable"]
        .agg(n="size", good="mean")
        .reset_index()
    )
    rates = rates[rates["n"] >= MIN_BUCKET_POLLS].copy()
    rates["disrupted_pct"] = (100 * (1 - rates["good"])).round(1)
    rates = rates[rates["disrupted_pct"] > 0]

    cols = ["line_id", f"worst_{by}", f"worst_{by}_disrupted_pct"]
    if rates.empty:
        return pd.DataFrame(columns=cols)

    worst = rates.loc[rates.groupby("line_id")["disrupted_pct"].idxmax()]
    return worst[["line_id", by, "disrupted_pct"]].set_axis(cols, axis=1)


def line_summary(per_poll: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    summary = (
        per_poll.groupby(["line_id", "line_name", "mode"])
        .agg(
            polls=("is_good", "size"),
            good_service_pct=("is_good", lambda x: round(100 * x.mean(), 1)),
            reliable_pct=("is_reliable", lambda x: round(100 * x.mean(), 1)),
        )
        .reset_index()
    )

    ep_counts = (
        episodes.groupby("line_id")
        .agg(episodes=("polls", "size"), disrupted_minutes=("duration_min", "sum"))
        .reset_index()
    )
    summary = summary.merge(ep_counts, on="line_id", how="left")
    summary["episodes"] = summary["episodes"].fillna(0).astype(int)
    summary["disrupted_minutes"] = summary["disrupted_minutes"].fillna(0).round(1)

    summary = summary.merge(disruption_rate(per_poll, "hour"), on="line_id", how="left")
    summary = summary.merge(disruption_rate(per_poll, "weekday"), on="line_id", how="left")
    return summary


def daily_summary(per_poll: pd.DataFrame) -> pd.DataFrame:
    return (
        per_poll.groupby(["date", "line_name"])
        .agg(
            polls=("is_good", "size"),
            good_service_pct=("is_good", lambda x: round(100 * x.mean(), 1)),
            reliable_pct=("is_reliable", lambda x: round(100 * x.mean(), 1)),
        )
        .reset_index()
    )


def main() -> None:
    if not IN_FILE.exists():
        print(f"{IN_FILE} not found. Run flatten.py first.")
        return

    per_poll = load_per_poll()
    episodes = find_episodes(per_poll)
    summary = line_summary(per_poll, episodes)
    daily = daily_summary(per_poll)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_DIR / "line_reliability.csv", index=False)
    episodes.to_csv(OUT_DIR / "episodes.csv", index=False)
    daily.to_csv(OUT_DIR / "daily_summary.csv", index=False)

    print(f"Polls per line: {per_poll.groupby('line_id').size().min()} to {per_poll.groupby('line_id').size().max()}")
    print(f"Days covered: {per_poll['date'].nunique()}\n")

    cols = ["line_name", "mode", "polls", "good_service_pct", "reliable_pct",
            "episodes", "disrupted_minutes", "worst_hour", "worst_weekday"]
    print(summary.sort_values("good_service_pct")[cols].to_string(index=False))
    print(f"\nWrote {OUT_DIR / 'line_reliability.csv'}, episodes.csv and daily_summary.csv")


if __name__ == "__main__":
    main()