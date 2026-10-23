from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA = Path("data/processed")
LOCAL_TZ = "Europe/London"

st.set_page_config(page_title="TfL Reliability", layout="wide")


@st.cache_data
def load():
    summary = pd.read_csv(DATA / "line_reliability.csv")

    daily = pd.read_csv(DATA / "daily_summary.csv")
    daily["date"] = pd.to_datetime(daily["date"])

    episodes = pd.read_csv(DATA / "episodes.csv")
    episodes["start_utc"] = pd.to_datetime(episodes["start_utc"], utc=True)
    episodes["end_utc"] = pd.to_datetime(episodes["end_utc"], utc=True)
    episodes["start_local"] = episodes["start_utc"].dt.tz_convert(LOCAL_TZ)
    episodes["end_local"] = episodes["end_utc"].dt.tz_convert(LOCAL_TZ)
    episodes["date"] = episodes["start_local"].dt.tz_localize(None).dt.normalize()

    return summary, daily, episodes


def main() -> None:
    if not (DATA / "line_reliability.csv").exists():
        st.error("Processed files not found. Run flatten.py and metrics.py first.")
        return

    summary, daily, episodes = load()

    st.title("TfL Line Reliability")
    st.caption(
        f"Data from {daily['date'].min():%d %b %Y} to {daily['date'].max():%d %b %Y}. "
        "The first and last days are partial. Times are London time."
    )

    with st.expander("How reliability is measured"):
        st.markdown(
            "- **Reliable %**: share of polls where every status was Good Service, "
            "Planned Closure or Part Closure.\n"
            "- **Good service %**: share of polls in Good Service only.\n"
            "- **Episodes**: runs of consecutive unreliable polls. A gap of more than "
            "10 minutes starts a new episode.\n"
            "- **Service Closed** is excluded, because the line is not scheduled to run.\n"
            "- Polls are taken every 5 minutes, so percentages approximate the share of time."
        )

    with st.sidebar:
        st.header("Filters")
        line = st.selectbox("Line", sorted(summary["line_name"]))
        min_day = daily["date"].min().date()
        max_day = daily["date"].max().date()
        picked = st.date_input(
            "Date range (trend and episodes)",
            value=(min_day, max_day),
            min_value=min_day,
            max_value=max_day,
        )

    # date_input returns a single date while the user is still picking the second one.
    if not (isinstance(picked, tuple) and len(picked) == 2):
        st.info("Select an end date to apply the range.")
        return
    start, end = pd.Timestamp(picked[0]), pd.Timestamp(picked[1])

    # Comparison across lines
    st.subheader("All lines, full period")
    melted = summary.melt(
        id_vars="line_name",
        value_vars=["reliable_pct", "good_service_pct"],
        var_name="measure",
        value_name="percent",
    )
    melted["measure"] = melted["measure"].map(
        {"reliable_pct": "Reliable %", "good_service_pct": "Good service %"}
    )
    order = summary.sort_values("reliable_pct")["line_name"].tolist()
    fig = px.bar(
        melted,
        x="percent",
        y="line_name",
        color="measure",
        orientation="h",
        barmode="group",
        category_orders={"line_name": order},
        height=620,
        labels={"percent": "% of polls", "line_name": ""},
    )
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    # Selected line, full period
    st.subheader(f"{line}, full period")
    row = summary.loc[summary["line_name"] == line].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reliable %", f"{row['reliable_pct']:.1f}")
    c2.metric("Good service %", f"{row['good_service_pct']:.1f}")
    c3.metric("Episodes", int(row["episodes"]))
    c4.metric("Disrupted minutes", f"{row['disrupted_minutes']:,.0f}")

    # Daily trend, date range applied
    st.subheader(f"{line}, daily trend")
    trend_src = daily[
        (daily["line_name"] == line) & daily["date"].between(start, end)
    ]
    if trend_src.empty:
        st.info("No data in this date range.")
    else:
        trend = trend_src.melt(
            id_vars="date",
            value_vars=["reliable_pct", "good_service_pct"],
            var_name="measure",
            value_name="percent",
        )
        trend["measure"] = trend["measure"].map(
            {"reliable_pct": "Reliable %", "good_service_pct": "Good service %"}
        )
        fig = px.line(
            trend,
            x="date",
            y="percent",
            color="measure",
            markers=True,
            labels={"percent": "% of polls", "date": ""},
        )
        fig.update_layout(legend_title_text="", yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

    # Episodes, date range applied
    st.subheader(f"{line}, disruption episodes")
    ep = episodes[
        (episodes["line_name"] == line) & episodes["date"].between(start, end)
    ].sort_values("start_local", ascending=False)

    if ep.empty:
        st.info("No disruption episodes in this date range.")
    else:
        table = pd.DataFrame(
            {
                "Start": ep["start_local"].dt.strftime("%a %d %b %H:%M"),
                "End": ep["end_local"].dt.strftime("%a %d %b %H:%M"),
                "Duration (min)": ep["duration_min"],
                "Worst status": ep["worst_status"],
                "Polls": ep["polls"],
            }
        )
        st.dataframe(table, use_container_width=True, hide_index=True)

    st.caption(
        "The comparison and summary figures use the full period. "
        "The date range applies to the trend and the episode table only."
    )


if __name__ == "__main__":
    main()