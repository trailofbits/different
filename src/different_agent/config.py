from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelConfig:
    name: str = "gpt-5.2"
    provider: str = "openai"
    reasoning_effort: str | None = "xhigh"
    temperature: float = 0.0


@dataclass(frozen=True)
class ExtractConfig:
    since_days: int = 30
    max_commits: int = 50
    max_patch_lines: int = 400
    include_github: bool = True
    max_issues: int = 50
    max_prs: int = 50


@dataclass(frozen=True)
class ReportsConfig:
    html: bool = True


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig = ModelConfig()
    extract: ExtractConfig = ExtractConfig()
    reports: ReportsConfig = ReportsConfig()


def _get_table(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    value = cfg.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Config [{key}] must be a table/object")
    return value


def _get_str(table: dict[str, Any], key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Config value must be a string: {key}")
    return value


def _get_bool(table: dict[str, Any], key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Config value must be a bool: {key}")
    return value


def _get_int(table: dict[str, Any], key: str, default: int) -> int:
    value = table.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"Config value must be an int: {key}")
    return value


def _get_float(table: dict[str, Any], key: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, int):
        return float(value)
    if not isinstance(value, float):
        raise ValueError(f"Config value must be a float: {key}")
    return value


def load_config(path: Path) -> AppConfig:
    """Load config from TOML, or return defaults if file doesn't exist."""
    if not path.exists():
        return AppConfig()

    import tomllib

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config file must parse to a TOML object")

    model_raw = _get_table(raw, "model")
    extract_raw = _get_table(raw, "extract")
    reports_raw = _get_table(raw, "reports")

    model = ModelConfig(
        name=_get_str(model_raw, "name", ModelConfig.name),
        provider=_get_str(model_raw, "provider", ModelConfig.provider),
        reasoning_effort=model_raw.get("reasoning_effort", ModelConfig.reasoning_effort),
        temperature=_get_float(model_raw, "temperature", ModelConfig.temperature),
    )
    if model.reasoning_effort is not None and not isinstance(model.reasoning_effort, str):
        raise ValueError("Config value must be a string or null: model.reasoning_effort")

    extract = ExtractConfig(
        since_days=_get_int(extract_raw, "since_days", ExtractConfig.since_days),
        max_commits=_get_int(extract_raw, "max_commits", ExtractConfig.max_commits),
        max_patch_lines=_get_int(extract_raw, "max_patch_lines", ExtractConfig.max_patch_lines),
        include_github=_get_bool(extract_raw, "include_github", ExtractConfig.include_github),
        max_issues=_get_int(extract_raw, "max_issues", ExtractConfig.max_issues),
        max_prs=_get_int(extract_raw, "max_prs", ExtractConfig.max_prs),
    )

    reports = ReportsConfig(
        html=_get_bool(reports_raw, "html", ReportsConfig.html),
    )

    return AppConfig(model=model, extract=extract, reports=reports)
