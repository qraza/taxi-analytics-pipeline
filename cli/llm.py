import httpx
import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
API_URL = "https://api.anthropic.com/v1/messages"


def call_claude(prompt: str, max_tokens: int = 500) -> str:
    """Send a single-turn prompt to Claude and return the text response."""

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    response = httpx.post(
        API_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30.0
    )

    response.raise_for_status()
    return response.json()["content"][0]["text"]


def analyse_trips(data: list[dict], date: str, borough: str | None) -> str:
    """Send trip summary data to Claude for analysis."""

    # Format data as a readable table for the prompt
    rows = "\n".join([
        f"- {r['pickup_zone']} ({r['pickup_borough']}): "
        f"{r['total_trips']:,} trips, avg fare ${r['avg_fare_usd']:.2f}, "
        f"avg duration {r['avg_duration_minutes']:.1f} mins, "
        f"revenue ${r['total_revenue_usd']:,.2f}"
        for r in data
    ])

    location = f" in {borough}" if borough else ""
    prompt = f"""You are a data analyst reviewing NYC Yellow Taxi trip data.

Here is a summary of the top pickup zones{location} for {date}:

{rows}

Provide a concise analysis (3-5 sentences) covering:
- Which zones are busiest and why that might be
- Any patterns in fare amounts vs trip duration
- One actionable insight for taxi operators or city planners
"""

    return call_claude(prompt)
