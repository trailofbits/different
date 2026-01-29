from __future__ import annotations

from pathlib import Path

import pytest

from different_agent.config import AppConfig, _get_table, load_config


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.toml")
    assert isinstance(cfg, AppConfig)
    assert cfg.model.name == "gpt-5.2"
    assert cfg.extract.since_days == 30
    assert cfg.reports.html is True


def test_load_config_parses_values(tmp_path: Path) -> None:
    config_text = """
[model]
name = "claude-sonnet-4"
provider = "anthropic"
reasoning_effort = "medium"
temperature = 0.2

[extract]
since_date = "2024-01-01"
since_days = 14
max_commits = 12
max_patch_lines = 123
include_github = false
max_issues = 5
max_prs = 6
from_pr = 10
to_pr = 20

[reports]
html = false
""".strip()
    path = tmp_path / "config.toml"
    path.write_text(config_text, encoding="utf-8")

    cfg = load_config(path)
    assert cfg.model.name == "claude-sonnet-4"
    assert cfg.model.provider == "anthropic"
    assert cfg.model.reasoning_effort == "medium"
    assert cfg.model.temperature == 0.2
    assert cfg.extract.since_date == "2024-01-01"
    assert cfg.extract.since_days == 14
    assert cfg.extract.max_commits == 12
    assert cfg.extract.max_patch_lines == 123
    assert cfg.extract.include_github is False
    assert cfg.extract.max_issues == 5
    assert cfg.extract.max_prs == 6
    assert cfg.extract.from_pr == 10
    assert cfg.extract.to_pr == 20
    assert cfg.reports.html is False


def test_load_config_rejects_invalid_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model = "oops"', encoding="utf-8")
    with pytest.raises(ValueError, match=r"Config \[model\] must be a table/object"):
        load_config(path)


def test_get_table_rejects_non_table() -> None:
    with pytest.raises(ValueError, match=r"Config \[model\] must be a table/object"):
        _get_table({"model": "bad"}, "model")
