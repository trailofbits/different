from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

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
    since_days = getattr(args, "since_days", None)
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
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]
    for noisy_logger in ("langchain", "langchain_core", "httpx", "openai", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def main() -> int:
    _configure_logging()
    logger.info("starting different-agent")
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
        required=True,
        help="Path to target git repo",
    )
    parser.add_argument(
        "--since-days", type=int, default=None, help="Override extract.since_days"
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
    cfg_path = _default_config_path(args.config)
    logger.info("loading config path=%s", cfg_path)
    cfg = load_config(cfg_path)
    cfg = _apply_cli_overrides(cfg, args)
    logger.info(
        "config model=%s provider=%s reasoning_effort=%s temperature=%s",
        cfg.model.name,
        cfg.model.provider,
        cfg.model.reasoning_effort,
        cfg.model.temperature,
    )
    logger.info(
        "config extract since_days=%s max_commits=%s max_patch_lines=%s include_github=%s",
        cfg.extract.since_days,
        cfg.extract.max_commits,
        cfg.extract.max_patch_lines,
        cfg.extract.include_github,
    )
    logger.info(
        "config extract max_issues=%s max_prs=%s",
        cfg.extract.max_issues,
        cfg.extract.max_prs,
    )
    logger.info("config reports html=%s", cfg.reports.html)

    resolved = create_chat_model(
        model_name=cfg.model.name,
        provider=cfg.model.provider,
        temperature=cfg.model.temperature,
        reasoning_effort=cfg.model.reasoning_effort,
    )
    logger.info("model resolved provider=%s name=%s", resolved.provider, resolved.name)

    inspiration_path = os.path.abspath(args.inspiration)
    target_path = os.path.abspath(args.target)
    logger.info(
        "run start inspiration_path=%s target_path=%s",
        inspiration_path,
        target_path,
    )
    _ensure_git_repo(inspiration_path)
    _ensure_git_repo(target_path)

    extract_agent = create_inspiration_agent(resolved.model)
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
    logger.info("invoking inspiration agent")
    extract_result = extract_agent.invoke(
        {"messages": [{"role": "user", "content": extract_prompt}]}
    )
    logger.info("inspiration agent finished")
    findings_json = _extract_state_file(extract_result, "/outputs/findings.json")
    if findings_json is None:
        raise SystemExit("Agent did not write /outputs/findings.json")
    findings_out_path = Path(args.findings_out)
    _write_output_json(findings_out_path, findings_json)
    logger.info("wrote findings json path=%s", findings_out_path)
    if cfg.reports.html:
        findings = json.loads(findings_json)
        if isinstance(findings, list):
            html_path = findings_out_path.with_suffix(".html")
            _write_output_html(html_path, render_findings_html(findings))
            logger.info("wrote findings html path=%s", html_path)

    # Provide the findings JSON to the target agent as an in-memory file.
    # DeepAgents' StateBackend expects FileData objects (content as list of lines).
    initial_files = {
        "/inputs/findings.json": {
            "content": findings_json.splitlines(),
            "created_at": "1970-01-01T00:00:00Z",
            "modified_at": "1970-01-01T00:00:00Z",
        }
    }

    target_agent = create_target_agent(resolved.model)
    target_prompt = (
        "Check this target repository for applicability of the findings in "
        "/inputs/findings.json.\n\n"
        f"target_repo_path: {target_path}\n"
    )
    logger.info("invoking target agent")
    target_result = target_agent.invoke(
        {"messages": [{"role": "user", "content": target_prompt}], "files": initial_files}
    )
    logger.info("target agent finished")
    assessment_json = _extract_state_file(target_result, "/outputs/target_assessment.json")
    if assessment_json is None:
        raise SystemExit("Agent did not write /outputs/target_assessment.json")
    assessment_out_path = Path(args.assessment_out)
    _write_output_json(assessment_out_path, assessment_json)
    logger.info("wrote target assessment json path=%s", assessment_out_path)
    if cfg.reports.html:
        assessments = json.loads(assessment_json)
        if isinstance(assessments, list):
            html_path = assessment_out_path.with_suffix(".html")
            _write_output_html(html_path, render_target_assessment_html(assessments))
            logger.info("wrote target assessment html path=%s", html_path)

    return 0
