from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from different_agent import cli
from different_agent.config import AppConfig, ExtractConfig, ModelConfig, ReportsConfig


def test_output_helpers() -> None:
    fixed = datetime(2024, 1, 2, 3, 4, tzinfo=UTC)
    assert cli._output_suffix(fixed) == "01-02_03-04"

    assert cli._output_project_name("/home/test/inspiration", None) == "inspiration"
    assert cli._output_project_name("/home/test/inspiration", "/home/test/target") == "target"
    assert cli._output_project_name("/", None) == "project"

    base = Path("outputs/findings.json")
    named = cli._apply_output_naming(base, "proj", "suffix")
    assert str(named) == str(Path("outputs") / "proj" / "findings_suffix.json")


def test_extract_state_file_and_structured_response() -> None:
    result = {"files": {"/outputs/findings.json": {"content": ["{", "}"]}}}
    assert cli._extract_state_file(result, "/outputs/findings.json") == "{\n}"
    assert cli._extract_state_file(result, "/outputs/missing.json") is None

    class Dummy:
        def model_dump(self):
            return {"items": [1, 2]}

    assert cli._structured_response_to_list(Dummy(), "items") == [1, 2]
    assert cli._structured_response_to_list({"items": [3]}, "items") == [3]
    assert cli._structured_response_to_list({"items": "nope"}, "items") is None


def test_sum_usage_and_cost() -> None:
    usage = {
        "model-a": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        "model-b": {"input_tokens": 1, "output_tokens": 1},
    }
    summary = cli._sum_usage_metadata(usage)
    assert summary == {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}

    class DummyMessage:
        def __init__(self, meta):
            self.response_metadata = meta

    results = [
        {"messages": [DummyMessage({"total_cost": 0.2})]},
        {"messages": [DummyMessage({"usage": {"total_cost": 0.3}})]},
    ]
    assert cli._sum_cost_from_results(results) == 0.5


def test_apply_cli_overrides_with_since_date(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2024, 1, 10, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, _tz=None):
            return fixed_now

    monkeypatch.setattr(cli, "datetime", FixedDateTime)

    cfg = AppConfig(
        model=ModelConfig(name="gpt-5.2", provider="openai"),
        extract=ExtractConfig(since_days=30),
        reports=ReportsConfig(html=True),
    )
    args = SimpleNamespace(
        model=None,
        since_days=None,
        since_date="2024-01-05",
        from_pr=None,
        to_pr=None,
        max_commits=None,
        max_patch_lines=None,
    )
    updated = cli._apply_cli_overrides(cfg, args)
    assert updated.extract.since_days == 5
    assert updated.extract.since_date == "2024-01-05"


def test_apply_cli_overrides_rejects_bad_ranges() -> None:
    cfg = AppConfig()
    args = SimpleNamespace(
        model=None,
        since_days=None,
        since_date=None,
        from_pr=10,
        to_pr=None,
        max_commits=None,
        max_patch_lines=None,
    )
    with pytest.raises(SystemExit, match="must be provided together"):
        cli._apply_cli_overrides(cfg, args)

    args = SimpleNamespace(
        model=None,
        since_days=None,
        since_date=None,
        from_pr=2,
        to_pr=1,
        max_commits=None,
        max_patch_lines=None,
    )
    with pytest.raises(SystemExit, match="must be <="):
        cli._apply_cli_overrides(cfg, args)

    future_date = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    args = SimpleNamespace(
        model=None,
        since_days=None,
        since_date=future_date,
        from_pr=None,
        to_pr=None,
        max_commits=None,
        max_patch_lines=None,
    )
    with pytest.raises(SystemExit, match="since_date must be in the past"):
        cli._apply_cli_overrides(cfg, args)
