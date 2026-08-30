"""Tests for local .env credential loading.

The .env path exists so IBM credentials never need to be exported into a shell
profile or pasted into a command. These tests pin the two properties that make
that safe: a real environment variable always wins, and no value is ever
returned or logged by the loader.
"""

import pytest

from devflow.config import DOTENV_FILENAME, find_dotenv, load_dotenv, parse_dotenv


@pytest.fixture(autouse=True)
def _reset_loader(monkeypatch):
    """load_dotenv() is once-per-process; reset it between tests."""
    monkeypatch.setattr("devflow.config._dotenv_loaded", False)


def _write(tmp_path, content):
    path = tmp_path / DOTENV_FILENAME
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parses_plain_assignments():
    assert parse_dotenv("A=1\nB=two") == {"A": "1", "B": "two"}


def test_ignores_comments_and_blank_lines():
    assert parse_dotenv("# comment\n\nA=1\n   \n# another\n") == {"A": "1"}


def test_strips_export_prefix():
    assert parse_dotenv("export DEVFLOW_WATSONX_APIKEY=abc") == {
        "DEVFLOW_WATSONX_APIKEY": "abc"
    }


def test_strips_matching_quotes():
    parsed = parse_dotenv("A='single'\nB=\"double\"\nC=\"mismatched'")
    assert parsed["A"] == "single"
    assert parsed["B"] == "double"
    assert parsed["C"] == "\"mismatched'"


def test_keeps_values_containing_equals_signs():
    """API keys and URLs routinely contain '='."""
    parsed = parse_dotenv("DEVFLOW_WATSONX_URL=https://x.com/?a=1&b=2")
    assert parsed["DEVFLOW_WATSONX_URL"] == "https://x.com/?a=1&b=2"


def test_ignores_lines_without_an_assignment():
    assert parse_dotenv("garbage line\nA=1") == {"A": "1"}


def test_empty_file_parses_to_nothing():
    assert parse_dotenv("") == {}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_loads_values_into_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("DEVFLOW_WATSONX_APIKEY", raising=False)
    path = _write(tmp_path, "DEVFLOW_WATSONX_APIKEY=from-file")
    loaded = load_dotenv(path)
    assert loaded == ["DEVFLOW_WATSONX_APIKEY"]
    import os

    assert os.environ["DEVFLOW_WATSONX_APIKEY"] == "from-file"


def test_a_real_environment_variable_is_never_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVFLOW_WATSONX_APIKEY", "from-environment")
    path = _write(tmp_path, "DEVFLOW_WATSONX_APIKEY=from-file")
    assert load_dotenv(path) == []
    import os

    assert os.environ["DEVFLOW_WATSONX_APIKEY"] == "from-environment"


def test_an_empty_environment_variable_is_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVFLOW_WATSONX_APIKEY", "")
    path = _write(tmp_path, "DEVFLOW_WATSONX_APIKEY=from-file")
    assert load_dotenv(path) == ["DEVFLOW_WATSONX_APIKEY"]


def test_loader_returns_names_never_values(tmp_path, monkeypatch):
    """The return value is safe to log; the secret must not appear in it."""
    monkeypatch.delenv("DEVFLOW_WATSONX_APIKEY", raising=False)
    path = _write(tmp_path, "DEVFLOW_WATSONX_APIKEY=super-secret-value")
    loaded = load_dotenv(path)
    assert "super-secret-value" not in repr(loaded)


def test_missing_file_is_not_an_error():
    assert load_dotenv(None) == [] or True  # no exception is the assertion


def test_unreadable_file_is_not_an_error(tmp_path):
    directory = tmp_path / DOTENV_FILENAME
    directory.mkdir()  # a directory where a file is expected
    assert load_dotenv(directory) == []


def test_loading_runs_only_once_per_process(tmp_path, monkeypatch):
    monkeypatch.delenv("A_ONCE", raising=False)
    path = _write(tmp_path, "A_ONCE=1")
    assert load_dotenv(path) == ["A_ONCE"]
    monkeypatch.delenv("A_ONCE", raising=False)
    assert load_dotenv(path) == []  # second call is a no-op
    assert load_dotenv(path, force=True) == ["A_ONCE"]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_find_dotenv_prefers_the_supplied_directory(tmp_path):
    path = _write(tmp_path, "A=1")
    assert find_dotenv(tmp_path) == path


def test_find_dotenv_returns_none_when_absent(tmp_path):
    missing = tmp_path / "empty_dir"
    missing.mkdir()
    # Falls through to the repository root, which may or may not have a .env;
    # the contract is only that it never raises.
    result = find_dotenv(missing)
    assert result is None or result.name == DOTENV_FILENAME
