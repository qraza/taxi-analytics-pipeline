import click
import pytest
from click.testing import CliRunner

from scripts.load_raw import (
    CI_DATA_DIR,
    CI_TRIPS_FILE,
    LOCAL_DATA_DIR,
    TRIPS_FILE,
    main,
    require_azure_config,
    resolve_local_source,
)


def test_resolve_local_source_defaults_to_local_data_dir():
    """--source local (and the default) should read from the local data dir."""
    assert resolve_local_source("local") == (LOCAL_DATA_DIR, TRIPS_FILE)


def test_resolve_local_source_ci_uses_fixtures():
    """--source ci should read from the committed CI fixture, not real data."""
    assert resolve_local_source("ci") == (CI_DATA_DIR, CI_TRIPS_FILE)


def test_require_azure_config_raises_with_no_real_call(monkeypatch):
    """missing Azure env vars should raise a friendly error naming both vars."""
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("CAPSTONE_AZURE_CONTAINER", raising=False)

    with pytest.raises(click.UsageError, match="AZURE_STORAGE_CONNECTION_STRING") as exc_info:
        require_azure_config()
    assert "CAPSTONE_AZURE_CONTAINER" in str(exc_info.value)


def test_source_azure_fails_fast_without_env(monkeypatch):
    """the CLI should exit non-zero with a clear message, no network/Azure calls made."""
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("CAPSTONE_AZURE_CONTAINER", raising=False)

    result = CliRunner().invoke(main, ["--source", "azure"])

    assert result.exit_code != 0
    assert "AZURE_STORAGE_CONNECTION_STRING" in result.output
    assert "CAPSTONE_AZURE_CONTAINER" in result.output
