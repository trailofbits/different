from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.tools import tool

from different_agent.git_tools import _run_git

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    repo: str


_ANALYZED_PRS: set[tuple[str, str, int]] = set()


def _record_analyzed_pr(owner: str | None, repo: str | None, number: int | None) -> None:
    if not owner or not repo or not isinstance(number, int):
        return
    _ANALYZED_PRS.add((owner, repo, number))


def get_analyzed_pr_count() -> int:
    return len(_ANALYZED_PRS)


def reset_analyzed_pr_count() -> None:
    _ANALYZED_PRS.clear()


def _github_token() -> str | None:
    return (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GITHUB_API_TOKEN")
        or os.environ.get("GH_TOKEN")
    )


def _github_request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "different-agent",
    }
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read().decode("utf-8")
        return json.loads(payload)


def _iso_since_days(since_days: int) -> str:
    dt = datetime.now(UTC) - timedelta(days=since_days)
    return dt.replace(microsecond=0).isoformat()


def _parse_github_repo_from_remote(remote_url: str) -> GitHubRepo | None:
    remote_url = remote_url.strip()
    if not remote_url:
        return None

    # git@github.com:owner/repo.git
    m = re.match(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", remote_url)
    if m:
        return GitHubRepo(owner=m.group("owner"), repo=m.group("repo"))

    # https://github.com/owner/repo(.git)
    try:
        parsed = urllib.parse.urlparse(remote_url)
    except Exception:
        return None

    if parsed.netloc != "github.com":
        return None

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    repo = repo.removesuffix(".git")
    if not owner or not repo:
        return None
    return GitHubRepo(owner=owner, repo=repo)


@tool
def git_github_repo(repo_path: str, remote: str = "origin") -> dict:
    """Resolve a local repo's GitHub {owner, repo} from its git remote URL."""
    logger.info("Resolving GitHub repo from %s (remote=%s).", repo_path, remote)
    try:
        out = _run_git(repo_path, ["remote", "get-url", remote]).stdout.strip()
    except Exception as e:
        return {"error": f"Failed to read git remote '{remote}': {e}"}
    resolved = _parse_github_repo_from_remote(out)
    if resolved is None:
        return {"error": f"Could not parse a github.com remote from: {out}"}
    return {"owner": resolved.owner, "repo": resolved.repo}


@tool
def github_recent_issues(
    owner: str, repo: str, since_days: int = 30, max_count: int = 50
) -> list[dict]:
    """Fetch recent closed issues from GitHub (excludes PRs)."""
    logger.info(
        "Fetching recent issues for %s/%s (since_days=%s, max_count=%s).",
        owner,
        repo,
        since_days,
        max_count,
    )
    since = _iso_since_days(since_days)
    query = urllib.parse.urlencode(
        {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": "100",
            "since": since,
        }
    )
    url = f"https://api.github.com/repos/{owner}/{repo}/issues?{query}"
    try:
        items = _github_request_json(url)
    except Exception as e:
        return [{"error": f"GitHub request failed: {e}"}]
    if not isinstance(items, list):
        return [{"error": "Unexpected response from GitHub issues API"}]

    results: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "pull_request" in item:
            continue
        results.append(
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "labels": [
                    label.get("name") for label in item.get("labels", []) if isinstance(label, dict)
                ],
                "closed_at": item.get("closed_at"),
                "updated_at": item.get("updated_at"),
                "html_url": item.get("html_url"),
                "body": (item.get("body") or "")[:4000],
            }
        )
        if len(results) >= max_count:
            break
    logger.info("Fetched %s issues.", len(results))
    return results


@tool
def github_recent_prs(
    owner: str,
    repo: str,
    since_days: int = 30,
    max_count: int = 50,
    from_pr: int | None = None,
    to_pr: int | None = None,
) -> list[dict]:
    """Fetch recent merged/closed PRs from GitHub (optionally by PR number range)."""
    logger.info(
        "Fetching recent PRs for %s/%s (since_days=%s, max_count=%s, from_pr=%s, to_pr=%s).",
        owner,
        repo,
        since_days,
        max_count,
        from_pr,
        to_pr,
    )
    if from_pr is not None or to_pr is not None:
        if from_pr is None or to_pr is None:
            return [{"error": "from_pr and to_pr must both be provided"}]
        if from_pr <= 0 or to_pr <= 0:
            return [{"error": "from_pr and to_pr must be positive"}]
        if from_pr > to_pr:
            return [{"error": "from_pr must be <= to_pr"}]
        results: list[dict] = []
        for number in range(from_pr, to_pr + 1):
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
            try:
                item = _github_request_json(url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                return [{"error": f"GitHub request failed: {e}"}]
            except Exception as e:
                return [{"error": f"GitHub request failed: {e}"}]
            if not isinstance(item, dict):
                continue
            if item.get("state") != "closed":
                continue
            results.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "merged_at": item.get("merged_at"),
                    "updated_at": item.get("updated_at"),
                    "html_url": item.get("html_url"),
                }
            )
            _record_analyzed_pr(owner, repo, item.get("number"))
            if len(results) >= max_count:
                break
        logger.info("Fetched %s PRs.", len(results))
        return results

    threshold = datetime.now(UTC) - timedelta(days=since_days)
    query = urllib.parse.urlencode(
        {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": "100",
        }
    )
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}"
    try:
        items = _github_request_json(url)
    except Exception as e:
        return [{"error": f"GitHub request failed: {e}"}]
    if not isinstance(items, list):
        return [{"error": "Unexpected response from GitHub pulls API"}]

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        merged_at = item.get("merged_at")
        updated_at = item.get("updated_at")
        date_str = merged_at or updated_at
        if isinstance(date_str, str):
            try:
                dt = datetime.fromisoformat(date_str)
            except ValueError:
                dt = None
            if dt is not None and dt < threshold:
                continue
        results.append(
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "merged_at": merged_at,
                "updated_at": updated_at,
                "html_url": item.get("html_url"),
            }
        )
        _record_analyzed_pr(owner, repo, item.get("number"))
        if len(results) >= max_count:
            break
    logger.info("Fetched %s PRs.", len(results))
    return results


@tool
def github_fetch_issue(owner: str, repo: str, number: int) -> dict:
    """Fetch one issue from GitHub."""
    logger.info(
        "Fetching issue #%s for %s/%s.",
        number,
        owner,
        repo,
    )
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    try:
        item = _github_request_json(url)
    except Exception as e:
        return {"error": f"GitHub request failed: {e}"}
    if not isinstance(item, dict):
        return {"error": "Unexpected response from GitHub issue API"}
    return {
        "number": item.get("number"),
        "title": item.get("title"),
        "state": item.get("state"),
        "labels": [
            label.get("name") for label in item.get("labels", []) if isinstance(label, dict)
        ],
        "closed_at": item.get("closed_at"),
        "updated_at": item.get("updated_at"),
        "html_url": item.get("html_url"),
        "body": (item.get("body") or "")[:12000],
    }


@tool
def github_fetch_pr(owner: str, repo: str, number: int) -> dict:
    """Fetch one PR from GitHub (metadata)."""
    logger.info(
        "Fetching PR #%s for %s/%s.",
        number,
        owner,
        repo,
    )
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    try:
        item = _github_request_json(url)
    except Exception as e:
        return {"error": f"GitHub request failed: {e}"}
    if not isinstance(item, dict):
        return {"error": "Unexpected response from GitHub pull API"}
    return {
        "number": item.get("number"),
        "title": item.get("title"),
        "state": item.get("state"),
        "merged_at": item.get("merged_at"),
        "updated_at": item.get("updated_at"),
        "html_url": item.get("html_url"),
        "body": (item.get("body") or "")[:12000],
    }


@tool
def github_fetch_pr_files(owner: str, repo: str, number: int, max_files: int = 200) -> list[dict]:
    """Fetch PR changed files (+ per-file patch snippets when available)."""
    logger.info(
        "Fetching files for PR #%s in %s/%s (max_files=%s).",
        number,
        owner,
        repo,
        max_files,
    )
    files: list[dict] = []
    page = 1
    per_page = 100
    while len(files) < max_files:
        query = urllib.parse.urlencode({"per_page": str(per_page), "page": str(page)})
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files?{query}"
        try:
            items = _github_request_json(url)
        except Exception as e:
            return [{"error": f"GitHub request failed: {e}"}]
        if not isinstance(items, list):
            break
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            patch = item.get("patch")
            if isinstance(patch, str) and len(patch) > 8000:
                patch = patch[:8000] + "\n\n[patch truncated]"
            files.append(
                {
                    "filename": item.get("filename"),
                    "status": item.get("status"),
                    "additions": item.get("additions"),
                    "deletions": item.get("deletions"),
                    "changes": item.get("changes"),
                    "patch": patch,
                }
            )
            if len(files) >= max_files:
                break
        page += 1
    _record_analyzed_pr(owner, repo, number)
    return files
