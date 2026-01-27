from __future__ import annotations

import argparse
import json
import logging
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.cache.memory import InMemoryCache

from different_agent.agents import create_inspiration_agent, create_target_agent
from different_agent.config import AppConfig, load_config
from different_agent.model import create_chat_model
from different_agent.report import render_findings_html, render_target_assessment_html

logger = logging.getLogger(__name__)


class _ColorFormatter(logging.Formatter):
    _COLORS = {
        logging.DEBUG: "\x1b[36m",
        logging.INFO: "\x1b[32m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[35m",
    }
    _RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        original_level = record.levelname
        color = self._COLORS.get(record.levelno)
        if color:
            record.levelname = f"{color}{original_level}{self._RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_level


def _ensure_git_repo(path: str) -> None:
    git_dir = os.path.join(path, ".git")
    if not os.path.isdir(git_dir):
        raise SystemExit(f"Not a git repository (missing .git directory): {path}")


def _write_output_json(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parsed = json.loads(content)
    path.write_text(json.dumps(parsed, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _write_output_html(path: Path, html_content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_content, encoding="utf-8")


def _extract_state_file(result: dict, file_path: str) -> str | None:
    files = result.get("files") or {}
    file_data = files.get(file_path)
    if not file_data:
        return None
    content_lines = file_data.get("content")
    if not isinstance(content_lines, list):
        return None
    return "\n".join(str(line) for line in content_lines)


def _structured_response_to_list(structured_response: Any, key: str) -> list[Any] | None:
    if structured_response is None:
        return None
    if hasattr(structured_response, "model_dump"):
        data = structured_response.model_dump()
    elif hasattr(structured_response, "dict"):
        data = structured_response.dict()
    else:
        data = structured_response
    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return value
        return None
    return None


def _default_config_path(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    candidate = Path("different.toml")
    if candidate.exists():
        return candidate
    return candidate  # defaults (even if missing)


def _apply_cli_overrides(cfg: AppConfig, args: argparse.Namespace) -> AppConfig:
    model_name = args.model or cfg.model.name
    # Model provider/reasoning live in config; --model is the only per-run override requested.
    since_days_override = getattr(args, "since_days", None)
    since_date_override = getattr(args, "since_date", None)
    if since_date_override is not None:
        raw_since_date = since_date_override
        since_days_override = None
    elif since_days_override is None:
        raw_since_date = cfg.extract.since_date
    else:
        raw_since_date = None
    if since_days_override is None and raw_since_date is not None:
        try:
            parsed = datetime.fromisoformat(raw_since_date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SystemExit(
                "Invalid since_date. Use YYYY-MM-DD or an ISO-8601 datetime like "
                "2024-01-01T00:00:00Z."
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if parsed > now:
            raise SystemExit("since_date must be in the past.")
        delta_seconds = (now - parsed).total_seconds()
        since_days = max(1, math.ceil(delta_seconds / 86400))
        effective_since_date = raw_since_date
    else:
        since_days = (
            since_days_override if since_days_override is not None else cfg.extract.since_days
        )
        effective_since_date = None
    max_commits = getattr(args, "max_commits", None)
    max_patch_lines = getattr(args, "max_patch_lines", None)
    return AppConfig(
        model=cfg.model.__class__(
            name=model_name,
            provider=cfg.model.provider,
            reasoning_effort=cfg.model.reasoning_effort,
            temperature=cfg.model.temperature,
        ),
        extract=cfg.extract.__class__(
            since_date=effective_since_date,
            since_days=since_days if since_days is not None else cfg.extract.since_days,
            max_commits=max_commits if max_commits is not None else cfg.extract.max_commits,
            max_patch_lines=max_patch_lines
            if max_patch_lines is not None
            else cfg.extract.max_patch_lines,
            include_github=cfg.extract.include_github,
            max_issues=cfg.extract.max_issues,
            max_prs=cfg.extract.max_prs,
        ),
        reports=cfg.reports,
    )


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        _ColorFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]
    for noisy_logger in ("langchain", "langchain_core", "httpx", "openai", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def _sum_usage_metadata(usage_by_model: dict[str, Any]) -> dict[str, int] | None:
    if not usage_by_model:
        return None
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for usage in usage_by_model.values():
        if not isinstance(usage, dict):
            continue
        in_tokens = int(usage.get("input_tokens") or 0)
        out_tokens = int(usage.get("output_tokens") or 0)
        total = usage.get("total_tokens")
        if total is None:
            total = in_tokens + out_tokens
        input_tokens += in_tokens
        output_tokens += out_tokens
        total_tokens += int(total)
    if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _accumulate_cost(meta: Any, total: float) -> tuple[float, bool]:
    if not isinstance(meta, dict):
        return total, False
    for key in ("total_cost", "cost", "total_cost_usd"):
        value = meta.get(key)
        if isinstance(value, (int, float)):
            return total + float(value), True
    usage = meta.get("usage") or meta.get("token_usage")
    if isinstance(usage, dict):
        for key in ("total_cost", "cost", "total_cost_usd"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                return total + float(value), True
    return total, False


def _sum_cost_from_results(results: list[dict[str, Any]]) -> float | None:
    total_cost = 0.0
    found = False
    for result in results:
        for message in result.get("messages") or []:
            meta = getattr(message, "response_metadata", None)
            total_cost, hit = _accumulate_cost(meta, total_cost)
            found = found or hit
    return total_cost if found else None


def _log_run_usage(usage_by_model: dict[str, Any], results: list[dict[str, Any]]) -> None:
    total_cost = _sum_cost_from_results(results)
    if total_cost is not None:
        logger.info("Run cost: $%.6f.", total_cost)
        return
    usage_summary = _sum_usage_metadata(usage_by_model)
    if usage_summary is None:
        logger.info("Run usage: unavailable (no usage metadata returned).")
        return
    logger.info(
        "Run token usage: input=%s, output=%s, total=%s.",
        usage_summary["input_tokens"],
        usage_summary["output_tokens"],
        usage_summary["total_tokens"],
    )


def main() -> int:
    _configure_logging()
    logger.info("Starting different-agent.")
    load_dotenv()

    parser = argparse.ArgumentParser(prog="different-agent")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to TOML config (default: ./different.toml if present)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name to use (overrides config). Example: gpt-5.2 or claude-sonnet-4-5-20250929",
    )
    parser.add_argument(
        "--inspiration",
        required=True,
        help="Path to inspiration git repo",
    )
    parser.add_argument(
        "--target",
        required=False,
        help="Path to target git repo (required unless --extract-only)",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract findings from the inspiration repo; skip target analysis",
    )
    parser.add_argument("--since-days", type=int, default=None, help="Override extract.since_days")
    parser.add_argument(
        "--since-date",
        default=None,
        help="Override extract.since_date (YYYY-MM-DD or ISO-8601). Overrides since_days.",
    )
    parser.add_argument(
        "--max-commits", type=int, default=None, help="Override extract.max_commits"
    )
    parser.add_argument(
        "--max-patch-lines", type=int, default=None, help="Override extract.max_patch_lines"
    )
    parser.add_argument(
        "--findings-out",
        default="outputs/findings.json",
        help="Output path for extracted findings JSON",
    )
    parser.add_argument(
        "--assessment-out",
        default="outputs/target_assessment.json",
        help="Output path for target assessment JSON",
    )

    args = parser.parse_args()
    if not args.extract_only and not args.target:
        parser.error("--target is required unless --extract-only is set")
    if args.extract_only:
        logger.info("Extract-only enabled: skipping target analysis.")
    cfg_path = _default_config_path(args.config)
    logger.info("Loading config from %s.", cfg_path)
    cfg = load_config(cfg_path)
    cfg = _apply_cli_overrides(cfg, args)
    logger.info(
        "Using model %s with provider %s (reasoning_effort=%s, temperature=%s).",
        cfg.model.name,
        cfg.model.provider,
        cfg.model.reasoning_effort,
        cfg.model.temperature,
    )
    logger.info(
        "Extractor settings: since_date=%s, since_days=%s, max_commits=%s, "
        "max_patch_lines=%s, include_github=%s.",
        cfg.extract.since_date or "(none)",
        cfg.extract.since_days,
        cfg.extract.max_commits,
        cfg.extract.max_patch_lines,
        cfg.extract.include_github,
    )
    logger.info(
        "GitHub limits: max_issues=%s, max_prs=%s.",
        cfg.extract.max_issues,
        cfg.extract.max_prs,
    )
    logger.info("HTML reports enabled: %s.", cfg.reports.html)

    resolved = create_chat_model(
        model_name=cfg.model.name,
        provider=cfg.model.provider,
        temperature=cfg.model.temperature,
        reasoning_effort=cfg.model.reasoning_effort,
    )
    logger.info("Resolved model: provider=%s, name=%s.", resolved.provider, resolved.name)
    cache = InMemoryCache()

    inspiration_path = os.path.abspath(args.inspiration)
    target_path = os.path.abspath(args.target) if args.target else None
    logger.info(
        "Run starting. Inspiration repo: %s. Target repo: %s.",
        inspiration_path,
        target_path or "(skipped)",
    )
    _ensure_git_repo(inspiration_path)
    if not args.extract_only:
        assert target_path is not None
        _ensure_git_repo(target_path)

    extract_result: dict[str, Any] = {}
    target_result: dict[str, Any] = {}
    with get_usage_metadata_callback() as usage_cb:
        extract_agent = create_inspiration_agent(resolved.model, cache=cache)
        extract_prompt = (
            "Analyze this inspiration repository and write findings.\n\n"
            f"inspiration_repo_path: {inspiration_path}\n"
            f"since_days: {cfg.extract.since_days}\n"
            f"max_commits: {cfg.extract.max_commits}\n"
            f"max_patch_lines: {cfg.extract.max_patch_lines}\n"
            f"include_github: {cfg.extract.include_github}\n"
            f"max_issues: {cfg.extract.max_issues}\n"
            f"max_prs: {cfg.extract.max_prs}\n"
        )
        logger.info("Invoking inspiration agent.")
        extract_result = extract_agent.invoke(
            {"messages": [{"role": "user", "content": extract_prompt}]}
        )
        logger.info("Inspiration agent finished.")
        structured_findings = _structured_response_to_list(
            extract_result.get("structured_response"), "findings"
        )
        if structured_findings is not None:
            findings_json = json.dumps(structured_findings)
            logger.info("Using structured response for findings.")
        else:
            findings_json = _extract_state_file(extract_result, "/outputs/findings.json")
            if findings_json is None:
                raise SystemExit("Agent did not write /outputs/findings.json")
        findings_out_path = Path(args.findings_out)
        _write_output_json(findings_out_path, findings_json)
        logger.info("Wrote findings JSON to %s.", findings_out_path)
        if cfg.reports.html:
            findings = json.loads(findings_json)
            if isinstance(findings, list):
                html_path = findings_out_path.with_suffix(".html")
                _write_output_html(html_path, render_findings_html(findings))
                logger.info("Wrote findings HTML report to %s.", html_path)

        if not args.extract_only:
            # Provide the findings JSON to the target agent as an in-memory file.
            # DeepAgents' StateBackend expects FileData objects (content as list of lines).
            initial_files = {
                "/inputs/findings.json": {
                    "content": findings_json.splitlines(),
                    "created_at": "1970-01-01T00:00:00Z",
                    "modified_at": "1970-01-01T00:00:00Z",
                }
            }

            target_agent = create_target_agent(resolved.model, cache=cache)
            assert target_path is not None
            target_prompt = (
                "Check this target repository for applicability of the findings in "
                "/inputs/findings.json.\n\n"
                f"target_repo_path: {target_path}\n"
            )
            logger.info("Invoking target agent.")
            target_result = target_agent.invoke(
                {
                    "messages": [{"role": "user", "content": target_prompt}],
                    "files": initial_files,
                }
            )
            logger.info("Target agent finished.")
            structured_assessments = _structured_response_to_list(
                target_result.get("structured_response"), "assessments"
            )
            if structured_assessments is not None:
                assessment_json = json.dumps(structured_assessments)
                logger.info("Using structured response for target assessment.")
            else:
                assessment_json = _extract_state_file(
                    target_result, "/outputs/target_assessment.json"
                )
                if assessment_json is None:
                    raise SystemExit("Agent did not write /outputs/target_assessment.json")
            assessment_out_path = Path(args.assessment_out)
            _write_output_json(assessment_out_path, assessment_json)
            logger.info("Wrote target assessment JSON to %s.", assessment_out_path)
            if cfg.reports.html:
                assessments = json.loads(assessment_json)
                if isinstance(assessments, list):
                    html_path = assessment_out_path.with_suffix(".html")
                    _write_output_html(html_path, render_target_assessment_html(assessments))
                    logger.info("Wrote target assessment HTML report to %s.", html_path)

    results = [extract_result]
    if not args.extract_only:
        results.append(target_result)
    _log_run_usage(usage_cb.usage_metadata, results)
    return 0
