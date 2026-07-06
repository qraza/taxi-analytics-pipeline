import datetime
import os

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from cli.llm import analyse_trips, call_claude

DB_PATH = os.environ.get(
    "DBT_DB_PATH",
    os.path.expanduser("~/development/capstone-data-tool/data/capstone.duckdb")
)

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def show_api_key_notice():
    st.info(
        "Set the `ANTHROPIC_API_KEY` environment variable and restart the app "
        "to enable AI analysis.",
        icon="🔑",
    )


# ---------------------------------------------------------------------------
# Cached data access — every query selects from marts only, no business logic
# ---------------------------------------------------------------------------

@st.cache_data
def load_date_bounds() -> tuple[datetime.date, datetime.date]:
    conn = get_conn()
    row = conn.execute("SELECT min(trip_date), max(trip_date) FROM main.mart_daily_kpis").fetchone()
    conn.close()
    return row[0], row[1]


@st.cache_data
def load_boroughs() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT pickup_borough FROM main.mart_trip_summary ORDER BY 1"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


@st.cache_data
def load_trip_summary(trip_date: str, boroughs: tuple[str, ...], top_n: int) -> pd.DataFrame:
    conn = get_conn()
    placeholders = ",".join(["?"] * len(boroughs))
    df = conn.execute(
        f"""
        SELECT
            pickup_zone,
            pickup_borough,
            total_trips,
            avg_distance_miles,
            avg_duration_minutes,
            avg_fare_usd,
            avg_tip_usd,
            total_revenue_usd,
            avg_passengers
        FROM main.mart_trip_summary
        WHERE trip_date = ?
          AND pickup_borough IN ({placeholders})
        ORDER BY total_trips DESC
        LIMIT ?
        """,
        [trip_date, *boroughs, top_n],
    ).df()
    conn.close()
    return df


@st.cache_data
def load_month_kpis() -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        """
        SELECT
            sum(total_trips)                                        as total_trips,
            sum(total_revenue_usd)                                  as total_revenue_usd,
            sum(avg_fare_usd * total_trips) / sum(total_trips)      as avg_fare_usd,
            sum(avg_duration_minutes * total_trips) / sum(total_trips) as avg_duration_minutes
        FROM main.mart_daily_kpis
        """
    ).df()
    conn.close()
    return df


@st.cache_data
def load_daily_kpis() -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        "SELECT * FROM main.mart_daily_kpis ORDER BY trip_date"
    ).df()
    conn.close()
    return df


@st.cache_data
def load_top_zones_by_revenue(limit: int = 10) -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        """
        SELECT
            pickup_zone,
            pickup_borough,
            sum(total_revenue_usd) as total_revenue_usd,
            sum(total_trips)       as total_trips
        FROM main.mart_trip_summary
        GROUP BY 1, 2
        ORDER BY total_revenue_usd DESC
        LIMIT ?
        """,
        [limit],
    ).df()
    conn.close()
    return df


@st.cache_data
def load_borough_revenue() -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        """
        SELECT pickup_borough, sum(total_revenue_usd) as total_revenue_usd
        FROM main.mart_trip_summary
        GROUP BY 1
        ORDER BY total_revenue_usd DESC
        """
    ).df()
    conn.close()
    return df


@st.cache_data
def load_hourly_patterns() -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        "SELECT * FROM main.mart_hourly_patterns"
    ).df()
    conn.close()
    return df


@st.cache_data
def load_airport_split() -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        """
        SELECT
            sum(total_trips * airport_trip_share)       as airport_trips,
            sum(total_trips * (1 - airport_trip_share)) as non_airport_trips
        FROM main.mart_daily_kpis
        """
    ).df()
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def render_explorer():
    min_date, max_date = load_date_bounds()
    default_date = datetime.date(2024, 1, 15)
    if not (min_date <= default_date <= max_date):
        default_date = min_date

    boroughs = load_boroughs()

    with st.sidebar:
        st.header("Explorer filters")
        trip_date = st.date_input(
            "Date", value=default_date, min_value=min_date, max_value=max_date
        )
        selected_boroughs = st.multiselect("Borough", options=boroughs, default=boroughs)
        top_n = st.slider("Top N zones", min_value=5, max_value=50, value=10, step=5)

    if not selected_boroughs:
        st.warning("Select at least one borough.")
        return

    df = load_trip_summary(trip_date.isoformat(), tuple(selected_boroughs), top_n)

    st.subheader(f"Top {top_n} pickup zones — {trip_date.isoformat()}")

    if df.empty:
        st.info("No trips found for this date and borough selection.")
        return

    display_df = df.rename(columns={
        "pickup_zone": "Zone",
        "pickup_borough": "Borough",
        "total_trips": "Trips",
        "avg_distance_miles": "Avg Distance (mi)",
        "avg_duration_minutes": "Avg Duration (min)",
        "avg_fare_usd": "Avg Fare",
        "avg_tip_usd": "Avg Tip",
        "total_revenue_usd": "Revenue",
        "avg_passengers": "Avg Passengers",
    })
    st.dataframe(
        display_df,
        column_config={
            "Trips": st.column_config.NumberColumn(format="%d"),
            "Avg Distance (mi)": st.column_config.NumberColumn(format="%.2f"),
            "Avg Duration (min)": st.column_config.NumberColumn(format="%.1f"),
            "Avg Fare": st.column_config.NumberColumn(format="$%.2f"),
            "Avg Tip": st.column_config.NumberColumn(format="$%.2f"),
            "Revenue": st.column_config.NumberColumn(format="$%,.2f"),
            "Avg Passengers": st.column_config.NumberColumn(format="%.1f"),
        },
        hide_index=True,
        width="stretch",
    )

    if st.button("Analyse with AI"):
        if not has_api_key():
            show_api_key_notice()
        else:
            borough_label = ", ".join(selected_boroughs) if len(selected_boroughs) < len(boroughs) else None
            data = df[["pickup_zone", "pickup_borough", "total_trips", "avg_fare_usd",
                       "avg_duration_minutes", "total_revenue_usd"]].to_dict("records")
            try:
                with st.spinner("Asking Claude..."):
                    analysis = analyse_trips(data, trip_date.isoformat(), borough_label)
                st.markdown(analysis)
            except Exception as exc:
                st.error(f"AI analysis failed: {exc}")


def render_executive_overview():
    kpis = load_month_kpis().iloc[0]

    st.subheader("Month at a glance")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total trips", f"{kpis['total_trips']:,.0f}")
    c2.metric("Total revenue", f"${kpis['total_revenue_usd']:,.2f}")
    c3.metric("Avg fare", f"${kpis['avg_fare_usd']:,.2f}")
    c4.metric("Avg duration", f"{kpis['avg_duration_minutes']:.1f} min")

    daily = load_daily_kpis()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=daily["trip_date"], y=daily["total_trips"], name="Trips", marker_color="#4C78A8"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=daily["trip_date"], y=daily["total_revenue_usd"], name="Revenue (USD)",
                   marker_color="#F58518", mode="lines+markers"),
        secondary_y=True,
    )
    fig.update_layout(title="Daily trips and revenue", legend=dict(orientation="h", y=1.1))
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Trips", secondary_y=False, tickformat=",")
    fig.update_yaxes(title_text="Revenue (USD)", secondary_y=True, tickformat="$,.0f")
    st.plotly_chart(fig, width="stretch")

    col1, col2 = st.columns(2)

    with col1:
        top_zones = load_top_zones_by_revenue(10)
        fig_zones = px.bar(
            top_zones.sort_values("total_revenue_usd"),
            x="total_revenue_usd",
            y="pickup_zone",
            orientation="h",
            title="Top 10 zones by revenue",
            labels={"total_revenue_usd": "Revenue (USD)", "pickup_zone": "Pickup zone"},
        )
        fig_zones.update_xaxes(tickformat="$,.0f")
        st.plotly_chart(fig_zones, width="stretch")

    with col2:
        borough_rev = load_borough_revenue()
        fig_donut = px.pie(
            borough_rev,
            names="pickup_borough",
            values="total_revenue_usd",
            hole=0.45,
            title="Revenue share by borough",
        )
        fig_donut.update_traces(textinfo="label+percent")
        st.plotly_chart(fig_donut, width="stretch")


def render_operational_insights():
    hourly = load_hourly_patterns()

    st.subheader("Trip volume by day of week and hour")
    pivot = hourly.pivot(index="pickup_day_of_week", columns="pickup_hour", values="total_trips")
    pivot = pivot.reindex(DAY_ORDER)
    fig_heatmap = px.imshow(
        pivot,
        labels=dict(x="Hour of day", y="Day of week", color="Trips"),
        color_continuous_scale="Blues",
        aspect="auto",
        title="Trips by day of week x pickup hour",
    )
    fig_heatmap.update_xaxes(dtick=1)
    st.plotly_chart(fig_heatmap, width="stretch")

    col1, col2 = st.columns(2)

    with col1:
        split = load_airport_split().iloc[0]
        fig_airport = go.Figure(go.Pie(
            labels=["Airport", "Non-airport"],
            values=[split["airport_trips"], split["non_airport_trips"]],
            hole=0.45,
        ))
        fig_airport.update_layout(title="Airport vs non-airport trips")
        fig_airport.update_traces(textinfo="label+percent")
        st.plotly_chart(fig_airport, width="stretch")

    with col2:
        fig_tips = px.line(
            hourly,
            x="pickup_hour",
            y="avg_tip_pct",
            color="pickup_day_of_week",
            category_orders={"pickup_day_of_week": DAY_ORDER},
            title="Average tip % by hour",
            labels={"pickup_hour": "Hour of day", "avg_tip_pct": "Avg tip %",
                    "pickup_day_of_week": "Day"},
        )
        fig_tips.update_yaxes(tickformat=".0%")
        fig_tips.update_xaxes(dtick=1)
        st.plotly_chart(fig_tips, width="stretch")


def build_ai_analyst_prompt(question: str) -> str:
    kpis = load_month_kpis().iloc[0]
    top_zones = load_top_zones_by_revenue(5)

    zones_text = "\n".join(
        f"- {r.pickup_zone} ({r.pickup_borough}): ${r.total_revenue_usd:,.2f} revenue, "
        f"{r.total_trips:,.0f} trips"
        for r in top_zones.itertuples()
    )

    summary = (
        f"Month summary: {kpis['total_trips']:,.0f} trips, "
        f"${kpis['total_revenue_usd']:,.2f} total revenue, "
        f"avg fare ${kpis['avg_fare_usd']:,.2f}, "
        f"avg duration {kpis['avg_duration_minutes']:.1f} minutes.\n\n"
        f"Top 5 zones by revenue:\n{zones_text}"
    )

    return (
        "You are a data analyst answering questions about NYC Yellow Taxi trip data "
        "for January 2024.\n\n"
        f"{summary}\n\n"
        f"Question: {question}\n\n"
        "Answer concisely, grounded in the data above."
    )


def render_ai_analyst():
    st.subheader("Ask a question about the data")
    question = st.text_area("Question", placeholder="e.g. Which boroughs generate the most revenue per trip?")

    if st.button("Ask Claude"):
        if not question.strip():
            st.warning("Enter a question first.")
        elif not has_api_key():
            show_api_key_notice()
        else:
            try:
                with st.spinner("Asking Claude..."):
                    prompt = build_ai_analyst_prompt(question)
                    answer = call_claude(prompt)
                st.markdown(answer)
            except Exception as exc:
                st.error(f"AI analysis failed: {exc}")


def main():
    st.set_page_config(page_title="NYC Taxi Data Tool", layout="wide")
    st.title("NYC Yellow Taxi — Data Tool")

    tab_explorer, tab_exec, tab_ops, tab_ai = st.tabs(
        ["Explorer", "Executive Overview", "Operational Insights", "AI Analyst"]
    )

    with tab_explorer:
        render_explorer()
    with tab_exec:
        render_executive_overview()
    with tab_ops:
        render_operational_insights()
    with tab_ai:
        render_ai_analyst()


if __name__ == "__main__":
    main()
