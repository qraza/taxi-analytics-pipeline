import click
import duckdb
import os
from rich.console import Console
from rich.table import Table

console = Console()

DB_PATH = os.environ.get(
    "DBT_DB_PATH",
    os.path.expanduser("~/development/capstone-data-tool/data/capstone.duckdb")
)

def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)

@click.group()
def cli():
    """NYC TLC Taxi data tool — query and analyse trip data."""
    pass

@cli.command()
@click.option("--date", default="2024-01-01", help="Date to summarise (YYYY-MM-DD)")
@click.option("--borough", default=None, help="Filter by borough (e.g. Manhattan)")
@click.option("--top", default=10, help="Number of zones to show")
@click.option("--order-by", "order_by", default="total_trips",
              type=click.Choice(["total_trips", "total_revenue_usd", "avg_fare_usd"]),
              help="Column to sort by")
def summary(date, borough, top, order_by):
    """Show top pickup zones for a given date."""
    conn = get_conn()

    borough_filter = f"AND pickup_borough = '{borough}'" if borough else ""

    query = f"""
        SELECT
            trip_date,
            pickup_zone,
            pickup_borough,
            total_trips,
            avg_fare_usd,
            avg_duration_minutes,
            total_revenue_usd
        FROM main.mart_trip_summary
        WHERE trip_date = '{date}'
        {borough_filter}
        ORDER BY {order_by} DESC
        LIMIT {top}
    """

    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        console.print(f"[yellow]No data found for {date}[/yellow]")
        return

    table = Table(title=f"NYC Taxi Summary — {date}", show_lines=True)
    table.add_column("Zone", style="cyan")
    table.add_column("Borough", style="magenta")
    table.add_column("Trips", justify="right")
    table.add_column("Avg Fare", justify="right")
    table.add_column("Avg Mins", justify="right")
    table.add_column("Revenue", justify="right", style="green")

    for row in rows:
        table.add_row(
            str(row[1]),
            str(row[2]),
            f"{row[3]:,}",
            f"${row[4]:.2f}",
            f"{row[5]:.1f}",
            f"${row[6]:,.2f}"
        )

    console.print(table)

@cli.command()
@click.option("--date", default="2024-01-01", help="Date to analyse (YYYY-MM-DD)")
@click.option("--borough", default=None, help="Filter by borough")
@click.option("--top", default=10, help="Number of zones to include in analysis")
def analyse(date, borough, top):
    """Generate an LLM analysis of trip data for a given date."""
    from cli.llm import analyse_trips

    conn = get_conn()

    borough_filter = f"AND pickup_borough = '{borough}'" if borough else ""

    query = f"""
        SELECT
            pickup_zone,
            pickup_borough,
            total_trips,
            avg_fare_usd,
            avg_duration_minutes,
            total_revenue_usd
        FROM main.mart_trip_summary
        WHERE trip_date = '{date}'
        {borough_filter}
        ORDER BY total_trips DESC
        LIMIT {top}
    """

    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        console.print(f"[yellow]No data found for {date}[/yellow]")
        return

    data = [
        {
            "pickup_zone": r[0],
            "pickup_borough": r[1],
            "total_trips": r[2],
            "avg_fare_usd": r[3],
            "avg_duration_minutes": r[4],
            "total_revenue_usd": r[5],
        }
        for r in rows
    ]

    console.print(f"\n[bold]Analysing NYC Taxi data for {date}...[/bold]\n")

    analysis = analyse_trips(data, date, borough)
    console.print(analysis)

if __name__ == "__main__":
    cli()
