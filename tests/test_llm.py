import pytest

from cli.llm import analyse_trips, call_claude


def test_analyse_trips_requires_api_key(monkeypatch):
    """should raise a clear error when no API key is set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("cli.llm.ANTHROPIC_API_KEY", None)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        analyse_trips(
            [{"pickup_zone": "JFK Airport", "pickup_borough": "Queens",
              "total_trips": 100, "avg_fare_usd": 60.0,
              "avg_duration_minutes": 35.0, "total_revenue_usd": 6000.0}],
            date="2024-01-15",
            borough=None,
        )


def test_call_claude_requires_api_key(monkeypatch):
    """should raise a clear error when no API key is set."""
    monkeypatch.setattr("cli.llm.ANTHROPIC_API_KEY", None)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        call_claude("hello")


def test_call_claude_returns_response_text(monkeypatch):
    """should return the text of Claude's response on a successful call."""
    monkeypatch.setattr("cli.llm.ANTHROPIC_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"text": "42 trips analysed."}]}

    def fake_post(url, headers, json, timeout):
        return FakeResponse()

    monkeypatch.setattr("cli.llm.httpx.post", fake_post)

    assert call_claude("how many trips?") == "42 trips analysed."


def test_call_claude_passes_max_tokens_and_prompt(monkeypatch):
    """should forward the prompt and max_tokens through to the API payload."""
    monkeypatch.setattr("cli.llm.ANTHROPIC_API_KEY", "fake-key")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"text": "ok"}]}

    def fake_post(url, headers, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("cli.llm.httpx.post", fake_post)

    call_claude("what's busiest?", max_tokens=123)

    assert captured["json"]["max_tokens"] == 123
    assert captured["json"]["messages"][0]["content"] == "what's busiest?"
