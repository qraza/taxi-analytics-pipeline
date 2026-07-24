import datetime
import os

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from cli.llm import analyse_trips, call_claude
from reporting.deck_builder import build_deck
from reporting.figures import (
    DAY_ORDER,
    build_avg_tip_by_payment_method_fig,
    build_daily_trend_fig,
    build_hourly_heatmap_fig,
    build_payment_mix_by_borough_fig,
    build_payment_split_by_hour_fig,
    build_top_zones_fig,
)

load_dotenv()


def get_db_path() -> str:
    return os.environ.get(
        "DBT_DB_PATH",
        os.path.expanduser("~/development/capstone-data-tool/data/capstone.duckdb")
    )


def get_conn():
    return duckdb.connect(get_db_path(), read_only=True)


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
            sum(total_tip_usd)                                      as total_tip_usd,
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
def load_hourly_months() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT pickup_month FROM main.mart_hourly_patterns ORDER BY 1"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


@st.cache_data
def load_hourly_patterns(month: str) -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        "SELECT * FROM main.mart_hourly_patterns WHERE pickup_month = ?",
        [month],
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


@st.cache_data
def load_payment_mix_by_borough() -> pd.DataFrame:
    conn = get_conn()
    df = conn.execute(
        """
        SELECT
            pickup_borough,
            payment_method,
            sum(total_trips)                                  as total_trips,
            sum(avg_tip_usd * total_trips) / sum(total_trips) as avg_tip_usd
        FROM main.mart_payment_mix
        GROUP BY 1, 2
        """
    ).df()
    conn.close()
    df["trip_share"] = df["total_trips"] / df.groupby("pickup_borough")["total_trips"].transform("sum")
    return df


@st.cache_data
def load_payment_mix_by_hour(borough: str | None = None) -> pd.DataFrame:
    conn = get_conn()
    borough_filter = "WHERE pickup_borough = ?" if borough else ""
    params = [borough] if borough else []
    df = conn.execute(
        f"""
        SELECT
            pickup_hour,
            payment_method,
            sum(total_trips) as total_trips
        FROM main.mart_payment_mix
        {borough_filter}
        GROUP BY 1, 2
        """,
        params,
    ).df()
    conn.close()
    df["trip_share"] = df["total_trips"] / df.groupby("pickup_hour")["total_trips"].transform("sum")
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
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total trips", f"{kpis['total_trips']:,.0f}")
    c2.metric("Total revenue", f"${kpis['total_revenue_usd']:,.2f}")
    c3.metric("Total tips", f"${kpis['total_tip_usd']:,.2f}")
    c4.metric("Avg fare", f"${kpis['avg_fare_usd']:,.2f}")
    c5.metric("Avg duration", f"{kpis['avg_duration_minutes']:.1f} min")

    daily = load_daily_kpis()
    st.plotly_chart(build_daily_trend_fig(daily), width="stretch")

    col1, col2 = st.columns(2)

    with col1:
        top_zones = load_top_zones_by_revenue(10)
        st.plotly_chart(build_top_zones_fig(top_zones), width="stretch")

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

    st.divider()
    st.subheader("Board pack export")
    include_ai = st.checkbox("Include AI commentary", value=False)
    if st.button("📥 Download board pack (PPTX)"):
        if include_ai and not has_api_key():
            show_api_key_notice()
        else:
            month = pd.to_datetime(daily["trip_date"]).dt.strftime("%Y-%m").iloc[0]
            try:
                with st.spinner("Building deck..."):
                    deck = build_deck(get_db_path(), month=month, include_ai_commentary=include_ai)
                st.download_button(
                    "Save PPTX",
                    data=deck,
                    file_name=f"nyc_taxi_board_pack_{month}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            except Exception as exc:
                st.error(f"Deck generation failed: {exc}")


def render_operational_insights():
    months = load_hourly_months()
    selected_month = st.selectbox("Month", options=months, index=len(months) - 1)
    hourly = load_hourly_patterns(selected_month)

    st.subheader("Trip volume by day of week and hour")
    st.plotly_chart(build_hourly_heatmap_fig(hourly), width="stretch")

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


def render_payment_analysis():
    borough_mix = load_payment_mix_by_borough()

    st.subheader("Payment mix by borough")
    st.plotly_chart(build_payment_mix_by_borough_fig(borough_mix), width="stretch")

    st.subheader("Average tip by payment method")
    st.plotly_chart(build_avg_tip_by_payment_method_fig(borough_mix), width="stretch")

    st.subheader("How the payment split changes across the day")
    boroughs = sorted(borough_mix["pickup_borough"].unique())
    selected_borough = st.selectbox("Borough", options=["All boroughs", *boroughs])
    borough_filter = None if selected_borough == "All boroughs" else selected_borough
    hourly_mix = load_payment_mix_by_hour(borough_filter)
    st.plotly_chart(build_payment_split_by_hour_fig(hourly_mix), width="stretch")


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

    tab_explorer, tab_exec, tab_ops, tab_payment, tab_ai = st.tabs(
        ["Explorer", "Executive Overview", "Operational Insights", "Payment Analysis", "AI Analyst"]
    )

    with tab_explorer:
        render_explorer()
    with tab_exec:
        render_executive_overview()
    with tab_ops:
        render_operational_insights()
    with tab_payment:
        render_payment_analysis()
    with tab_ai:
        render_ai_analyst()


if __name__ == "__main__":
    main()
