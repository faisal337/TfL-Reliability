from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="TfL Reliability", layout="wide")

DATA = Path("data/processed")
LOCAL_TZ = "Europe/London"
WEEKDAYS = ["Sunday","Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DURATION_BINS = [0, 5, 15, 30, 60, 120, float("inf")]
DURATION_LABELS = ["5 min or less", "6 to 15", "16 to 30", "31 to 60", "61 to 120", "Over 120"]

STATUS_COLORS = {
    "Good Service": "#2e7d32",
    "Planned Closure": "#f9a825",
    "Part Closure": "#fb8c00",
    "Minor Delays": "#ef6c00",
    "Reduced Service": "#d84315",
    "Severe Delays": "#b71c1c",
    "Part Suspended": "#880e4f",
    "Suspended": "#4a148c",
}
STATE_COLORS = {
    "Good service": "#2e7d32",
    "Planned works": "#f9a825",
    "Unplanned disruption": "#c62828",
}

TAB_CSS = """
<style>
div[data-testid="stTabs"] [role="tablist"] { gap: 12px; }
div[data-testid="stTabs"] [role="tab"] {
    padding: 14px 32px;
    border-radius: 12px 12px 0 0;
    background-color: rgba(128, 128, 128, 0.18);
}
div[data-testid="stTabs"] [role="tab"] p {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0;
}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background-color: #ff6b35;
}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {
    color: #ffffff;
}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: #ff6b35;
}
</style>
"""

METHOD_MD = """
### Data sources
- **Line status:** TfL Unified API Line Status endpoint, for the Tube, Overground, DLR and Elizabeth line. Polled every 5 minutes from AWS Lambda and stored as raw JSON in S3.
- **Station crowding:** TfL crowding Live endpoint, one request per Underground station (about 270 stations), polled every 5 minutes.
- Both sources are collected continuously, so the period grows over time. The date range in the sidebar limits what is shown.

### Status classification
- Each poll records every status a line reports. Where a line reports more than one, the worst is kept, using a severity ranking. The ranking is our judgement: Good Service is best, then Minor Delays, Reduced Service, Part or Planned Closure, Severe Delays, Part Suspended, and Suspended.
- **Good service:** the line reports Good Service only.
- **Reliable:** every status is Good Service, Planned Closure or Part Closure. Planned works count as reliable in the headline, so the gap between reliable and good service is planned works. Planned works still affect passengers, so read reliable as "not unexpectedly disrupted".
- **Unplanned disruption:** any other status.
- **Service Closed** is excluded from every calculation, because the line is not scheduled to run.

### Episodes and disrupted minutes
- An episode is a run of consecutive unreliable polls on the same line. A gap of more than 10 minutes between polls starts a new episode.
- Episode duration runs from the first to the last unreliable poll, plus one 5-minute interval.
- Disrupted minutes are estimates from poll timing. They are not TfL's recorded disruption times.
- Each episode is counted on the day and hour it starts. An overnight episode is counted in full at its start time.

### Time conventions
- All times are London time.
- The service day runs from 04:00 to 04:00. Activity before 04:00 counts toward the previous day, so Friday night service after midnight counts as Friday.
- Hour-of-day charts use calendar hours, not service hours.

### Crowding
- Values are TfL's percentage of baseline for each station, multiplied by 100 for display on a 0 to 100 scale. We have not verified exactly how TfL defines the baseline, so check TfL's documentation before describing it as a share of capacity or as "full".
- Readings lag the poll by about 7 minutes. Station averages use only successful fetches where TfL reports data as available.
- A station that errors in a poll, for example because of rate limiting, is left out of that poll. It is not counted as zero.
- Crowding is measured per station. A station serves several lines, so crowding can't be linked to one line's reliability without more work.

### How to read the charts
- **Share of time by line:** the proportion of polls in each state, ordered by reliable %.
- **Reliability over time:** daily reliable % for each line. Partial first and last days are based on fewer polls, so they are less representative.
- **Delays heatmap:** episode minutes by service weekday and start hour. Each cell rests on only a few days, so a single bright cell can reflect one incident.
- **Crowding heatmap:** average crowding by station and hour across all recorded days.

### Limits
- The data covers a short period so far. Weekday and hour patterns need several weeks before they should be stated as findings. Check the caption for the exact dates.
- The clocks changed on 25 October, so that day has 25 hours of polls.
- Status reasons are free text from TfL. The planned and unplanned split currently uses status codes only, not the reason text.
- Polls are about 5 minutes apart but not exactly regular, so durations are approximate.
- Crowding history is shorter than status history, and TfL's crowding data covers Underground stations only.
- Nothing here shows causes. Any link between disruption and crowding is a correlation, not proof.
"""

def tidy(fig, height=None):
    """Consistent margins, a legend below the chart, and room for long axis labels."""
    layout = dict(  # noqa: C408
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(
            orientation="h", yanchor="top", y=-0.15,
            xanchor="left", x=0, title_text="",
        ),
    )
    if height:
        layout["height"] = height
    fig.update_layout(**layout)
    fig.update_yaxes(automargin=True)
    return fig


def read_optional(name: str):
    path = DATA / name
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def load_all():
    summary = pd.read_csv(DATA / "line_reliability.csv")
    daily = pd.read_csv(DATA / "daily_summary.csv", parse_dates=["date"])

    episodes = pd.read_csv(DATA / "episodes.csv")
    episodes["start_utc"] = pd.to_datetime(episodes["start_utc"], utc=True)
    episodes["end_utc"] = pd.to_datetime(episodes["end_utc"], utc=True)
    episodes["start_local"] = episodes["start_utc"].dt.tz_convert(LOCAL_TZ)
    episodes["end_local"] = episodes["end_utc"].dt.tz_convert(LOCAL_TZ)
    episodes["day"] = episodes["start_local"].dt.tz_localize(None).dt.normalize()

    crowd = read_optional("crowding_hourly.csv")
    if crowd is not None:
        # Safeguards for a file written before the flatten_crowding.py changes.
        crowd["station_name"] = crowd["station_name"].str.replace(
            r"\s+underground station$", "", case=False, regex=True
        )
        if crowd["avg_pct"].max() <= 1:
            crowd["avg_pct"] = crowd["avg_pct"] * 100

    return summary, daily, episodes, read_optional("hourly_profile.csv"), crowd


def line_period(daily: pd.DataFrame) -> pd.DataFrame:
    """Poll-weighted reliability per line over the filtered period."""
    g = daily.assign(
        r=daily["reliable_pct"] * daily["polls"],
        g=daily["good_service_pct"] * daily["polls"],
    )
    g = g.groupby("line_name").agg(
        polls=("polls", "sum"), r=("r", "sum"), g=("g", "sum")
    ).reset_index()
    g["reliable_pct"] = (g["r"] / g["polls"]).round(1)
    g["good_service_pct"] = (g["g"] / g["polls"]).round(1)
    return g[["line_name", "polls", "reliable_pct", "good_service_pct"]]


def disrupted_minutes_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """Estimated disrupted minutes per day per line (5 minutes per poll)."""
    d = daily.copy()
    d["disrupted_min"] = (100 - d["reliable_pct"]) / 100 * d["polls"] * 5
    return d.groupby(["date", "line_name"], as_index=False)["disrupted_min"].sum()

def fit_axis(fig, axis: str, max_value, pad: float = 0.08):
    """Set the axis range from the data maximum, so bars are never clipped."""
    if max_value and max_value > 0:
        update = fig.update_xaxes if axis == "x" else fig.update_yaxes
        update(range=[0, max_value * (1 + pad)])
    return fig

def main() -> None:
    st.markdown(TAB_CSS, unsafe_allow_html=True)

    if not (DATA / "line_reliability.csv").exists():
        st.error("Processed files not found. Run flatten.py and metrics.py first.")
        return

    summary, daily, episodes, hourly, crowd = load_all()
    all_lines = sorted(summary["line_name"].unique())

    with st.sidebar:
        st.header("Filters")
        min_day = daily["date"].min().date()
        max_day = daily["date"].max().date()
        picked = st.date_input(
            "Date range", (min_day, max_day), min_value=min_day, max_value=max_day
        )

    if not (isinstance(picked, tuple) and len(picked) == 2):
        st.info("Select an end date to apply the range.")
        return

    start = pd.Timestamp(picked[0])
    end = pd.Timestamp(picked[1]) + pd.Timedelta(days=1)
    daily_f = daily[(daily["date"] >= start) & (daily["date"] < end)]
    ep_f = episodes[(episodes["day"] >= start) & (episodes["day"] < end)]

    st.title("TfL Line Reliability and Crowding")
    st.caption(
        f"Status data {daily['date'].min():%d %b} to {daily['date'].max():%d %b %Y} "
        f"({summary['polls'].max()} polls per line). Times are London time. "
        "The first and last days are partial."
    )

    tab_overview, tab_delays, tab_crowd, tab_method = st.tabs(
        ["Overview", "Delays", "Crowding", "Method"]
    )

    # ---------- Overview ----------
    with tab_overview:
        period = line_period(daily_f)
        if period.empty:
            st.info("No data in this date range.")
        else:
            total_polls = period["polls"].sum()
            network_reliable = (period["reliable_pct"] * period["polls"]).sum() / total_polls

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Network reliable", f"{network_reliable:.1f}%")
            c2.metric("Disrupted line-hours", f"{ep_f['duration_min'].sum() / 60:,.0f}")
            c3.metric("Disruption episodes", f"{len(ep_f):,}")
            longest = ep_f["duration_min"].max()
            c4.metric("Longest episode", f"{longest:,.0f} min" if pd.notna(longest) else "None")

            st.subheader("Share of time by line")
            bars = period.assign(
                planned=(period["reliable_pct"] - period["good_service_pct"]).round(1),
                unplanned=(100 - period["reliable_pct"]).round(1),
            ).sort_values("reliable_pct")
            long = bars.melt(
                id_vars="line_name",
                value_vars=["good_service_pct", "planned", "unplanned"],
                var_name="state",
                value_name="percent",
            )
            long["state"] = long["state"].map({
                "good_service_pct": "Good service",
                "planned": "Planned works",
                "unplanned": "Unplanned disruption",
            })
            fig = px.bar(
                long,
                x="percent",
                y="line_name",
                color="state",
                orientation="h",
                barmode="stack",
                color_discrete_map=STATE_COLORS,
                category_orders={"line_name": bars["line_name"].tolist()},
                labels={"percent": "% of polls", "line_name": "", "state": ""},
            )
            st.plotly_chart(tidy(fig, height=620), use_container_width=True)

            st.subheader("Reliability over time")
            worst_four = bars["line_name"].tolist()[:4]
            sel = st.multiselect(
                "Lines to compare", all_lines, default=worst_four, key="trend_lines"
            )
            trend = daily_f[daily_f["line_name"].isin(sel)]
            if trend.empty:
                st.info("Select at least one line.")
            else:
                fig = px.line(
                    trend,
                    x="date",
                    y="reliable_pct",
                    color="line_name",
                    markers=True,
                    labels={"reliable_pct": "Reliable %", "date": "", "line_name": "Line"},
                )
                fig.update_yaxes(range=[0, 100])
                st.plotly_chart(tidy(fig), use_container_width=True)

            if hourly is not None:
                st.subheader("When disruption happens (hour of day)")
                h = hourly[hourly["line_name"].isin(sel)].copy()
                h["unreliable_pct"] = (100 - h["reliable_pct"]).round(1)
                fig = px.line(
                    h,
                    x="hour",
                    y="unreliable_pct",
                    color="line_name",
                    markers=True,
                    labels={
                        "hour": "Hour (London)",
                        "unreliable_pct": "% of polls disrupted",
                        "line_name": "Line",
                    },
                )
                st.plotly_chart(tidy(fig), use_container_width=True)
                st.caption(
                    "Calendar hour, full period. Each point has only a few days of "
                    "observations, so read the shape, not single values."
                )

    # ---------- Delays ----------
    with tab_delays:
        lines_sel = st.multiselect(
            "Lines", all_lines, default=all_lines, key="delay_lines"
        )
        e = ep_f[ep_f["line_name"].isin(lines_sel)]

        if e.empty:
            st.info("No disruption episodes for these lines in this date range.")
        else:
            st.subheader("Disruption timeline")
            fig = px.timeline(
                e,
                x_start="start_local",
                x_end="end_local",
                y="line_name",
                color="worst_status",
                color_discrete_map=STATUS_COLORS,
                hover_data={"duration_min": True, "polls": True},
                category_orders={"line_name": sorted(lines_sel)},
                labels={"worst_status": "Worst status", "line_name": ""},
            )
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(
                tidy(fig, height=max(400, 28 * len(lines_sel) + 150)),
                use_container_width=True,
            )

            left, right = st.columns(2)
            with left:
                st.subheader("Episodes by severity")
                counts = (
                    e.groupby(["line_name", "worst_status"])
                    .size()
                    .reset_index(name="episodes")
                )
                fig = px.bar(
                    counts,
                    x="episodes",
                    y="line_name",
                    color="worst_status",
                    orientation="h",
                    barmode="stack",
                    color_discrete_map=STATUS_COLORS,
                    labels={"line_name": "", "worst_status": "Worst status"},
                )
                st.plotly_chart(tidy(fig, height=500), use_container_width=True)

            with right:
                st.subheader("Disrupted minutes by line")
                mins = (
                    e.groupby("line_name", as_index=False)["duration_min"]
                    .sum()
                    .sort_values("duration_min")
                )
                fig = px.bar(
                    mins,
                    x="duration_min",
                    y="line_name",
                    orientation="h",
                    labels={"duration_min": "Disrupted minutes", "line_name": ""},
                )
                fit_axis(fig, "x", mins["duration_min"].max())
                st.plotly_chart(tidy(fig, height=500), use_container_width=True)

            st.subheader("How long episodes last")
            e_b = e.assign(bucket=pd.cut(
                e["duration_min"], bins=DURATION_BINS, labels=DURATION_LABELS, include_lowest=True,
            ))
            buckets = (
                e_b.groupby("bucket", observed=False)
                .size()
                .reset_index(name="episodes")
            )
            fig = px.bar(
                buckets,
                x="bucket",
                y="episodes",
                labels={"bucket": "Episode length", "episodes": "Episodes"},
                color_discrete_sequence=["#3b6fb6"],
            )
            st.plotly_chart(tidy(fig, height=380), use_container_width=True)

            st.subheader("Longest episodes")
            top = e.nlargest(15, "duration_min")[
                ["start_local", "line_name", "worst_status", "duration_min", "polls"]
            ].copy()
            top["start_local"] = top["start_local"].dt.strftime("%a %d %b %H:%M")
            top = top.rename(columns={
                "start_local": "Start",
                "line_name": "Line",
                "worst_status": "Worst status",
                "duration_min": "Duration (min)",
                "polls": "Polls",
            })
            st.dataframe(top, hide_index=True, use_container_width=True)

            st.subheader("When delays cluster")
            service_day = e["start_local"] - pd.Timedelta(hours=4)  # same cutoff as metrics.py
            e2 = e.assign(
                weekday=service_day.dt.day_name(),
                hour=e["start_local"].dt.hour,
            )
            heat = (
                e2.pivot_table(
                    index="weekday",
                    columns="hour",
                    values="duration_min",
                    aggfunc="sum",
                    fill_value=0,
                )
                .reindex(WEEKDAYS)
                .fillna(0)
            )
            fig = px.imshow(
                heat,
                aspect="auto",
                color_continuous_scale="Cividis",
                labels={
                    "x": "Hour episode started (London)",
                    "y": "",
                    "color": "Disrupted minutes",
                },
            )
            st.plotly_chart(tidy(fig, height=360), use_container_width=True)
            st.caption(
                "Weekday uses the service day (before 04:00 counts as the previous day). "
                "Eight days gives one or two observations per weekday, so treat this as a first look."
            )

            st.subheader("Disrupted minutes per day")
            dm = disrupted_minutes_daily(daily_f[daily_f["line_name"].isin(lines_sel)])
            fig = px.bar(
                dm,
                x="date",
                y="disrupted_min",
                color="line_name",
                barmode="stack",
                labels={"disrupted_min": "Disrupted minutes", "date": "", "line_name": "Line"},
            )
            # Stacked bars: the axis must fit the largest day total, not the largest single segment.
            fit_axis(fig, "y", dm.groupby("date")["disrupted_min"].sum().max())
            st.plotly_chart(tidy(fig, height=480), use_container_width=True)

    # ---------- Crowding ----------
    with tab_crowd:
        if crowd is None:
            st.info("Crowding summary not generated yet. Run flatten_crowding.py.")
        else:
            st.caption(
                f"Average crowding by hour, from {int(crowd['n'].sum()):,} readings so far. "
                "Early data: treat the pattern as provisional until about two weeks have been collected."
            )
            top_n = st.slider("Stations shown (busiest first)", 10, 60, 30, key="crowd_n")
            fixed = st.toggle(
                "Fixed 0 to 100 scale",
                value=True,
                key="crowd_fixed",
                help="Off: the colour scale stretches to the busiest value, which shows small differences.",
            )

            pivot = crowd.pivot_table(index="station_name", columns="hour", values="avg_pct")
            order = pivot.mean(axis=1).sort_values(ascending=False).head(top_n).index
            pivot = pivot.loc[sorted(order)]

            st.subheader("Crowding by station and hour")
            fig = px.imshow(
                pivot,
                aspect="auto",
                color_continuous_scale="Viridis",
                zmin=0 if fixed else None,
                zmax=100 if fixed else None,
                labels={"x": "Hour (London)", "y": "", "color": "% of baseline"},
            )
            st.plotly_chart(tidy(fig, height=max(400, 22 * top_n)), use_container_width=True)

            st.subheader("Network average by hour")
            profile = crowd.groupby("hour", as_index=False)["avg_pct"].mean()
            fig = px.line(
                profile,
                x="hour",
                y="avg_pct",
                markers=True,
                labels={"hour": "Hour (London)", "avg_pct": "Average % of baseline"},
            )
            fig.update_yaxes(range=[0, 100])
            st.plotly_chart(tidy(fig, height=360), use_container_width=True)

    # ---------- Method ----------
    with tab_method:
        st.markdown(METHOD_MD)

if __name__ == "__main__":
    main()