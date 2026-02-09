from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


_ANALYZED_COMMITS: set[str] = set()


def _record_analyzed_commit(sha: str | None) -> None:
    if sha:
        _ANALYZED_COMMITS.add(sha)


def get_analyzed_commit_count() -> int:
    return len(_ANALYZED_COMMITS)


def reset_analyzed_commit_count() -> None:
    _ANALYZED_COMMITS.clear()


@dataclass(frozen=True)
class GitCommandResult:
    stdout: str


def _ensure_git_repo(repo_path: str) -> None:
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        msg = f"Not a git repo (missing .git directory): {repo_path}"
        raise ValueError(msg)


def _run_git(repo_path: str, args: list[str]) -> GitCommandResult:
    _ensure_git_repo(repo_path)
    cmd = ["git", "-C", repo_path, *args]
    logger.debug("Running git command in %s: %s.", repo_path, args)
    completed = subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
    )
    return GitCommandResult(stdout=completed.stdout)


@tool
def git_recent_commits(repo_path: str, since_days: int = 30, max_count: int = 50) -> list[dict]:
    """Return recent commits for a repository (metadata only, no diffs)."""
    logger.info(
        "Reading recent commits from %s (since_days=%s, max_count=%s).",
        repo_path,
        since_days,
        max_count,
    )
    if since_days <= 0:
        raise ValueError("since_days must be > 0")
    if max_count <= 0:
        raise ValueError("max_count must be > 0")

    # Use record/field separators that won't appear in normal text.
    # Each record: sha, author_name, author_date, subject
    fmt = "%H%x1f%an%x1f%ad%x1f%s%x1e"
    out = _run_git(
        repo_path,
        [
            "log",
            f"--since={since_days} days ago",
            f"--max-count={max_count}",
            "--date=iso-strict",
            f"--pretty=format:{fmt}",
        ],
    ).stdout

    commits: list[dict] = []
    for record in out.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        sha, author, date, subject = record.split("\x1f")
        commits.append(
            {
                "sha": sha,
                "author": author,
                "date": date,
                "subject": subject,
            }
        )
    logger.info("Found %s recent commits.", len(commits))
    return commits


@tool
def git_show_commit(repo_path: str, sha: str, max_patch_lines: int = 400) -> dict:
    """Return commit metadata + file list + a truncated patch."""
    logger.info(
        "Loading commit %s from %s (max_patch_lines=%s).",
        sha,
        repo_path,
        max_patch_lines,
    )
    if max_patch_lines <= 0:
        raise ValueError("max_patch_lines must be > 0")

    meta_fmt = "%H%x1f%an%x1f%ad%x1f%s%x1f%b"
    meta = _run_git(
        repo_path,
        [
            "show",
            "--no-color",
            "--date=iso-strict",
            f"--pretty=format:{meta_fmt}",
            "--name-status",
            "--no-patch",
            sha,
        ],
    ).stdout

    # Split header and name-status list
    meta_line, *file_lines = meta.splitlines()
    commit_sha, author, date, subject, body = meta_line.split("\x1f")
    files_changed: list[dict] = []
    for line in file_lines:
        line = line.strip()
        if not line:
            continue
        # name-status: <status>\t<path>
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts
        files_changed.append({"status": status, "path": path})

    patch = _run_git(
        repo_path,
        [
            "show",
            "--no-color",
            "--format=",
            "--patch",
            sha,
        ],
    ).stdout
    patch_lines = patch.splitlines()
    truncated = False
    if len(patch_lines) > max_patch_lines:
        patch = "\n".join(patch_lines[:max_patch_lines]) + "\n\n[patch truncated]"
        truncated = True

    logger.info(
        "Loaded commit metadata. Files changed: %s. Patch truncated: %s.",
        len(files_changed),
        truncated,
    )
    _record_analyzed_commit(commit_sha)
    return {
        "sha": commit_sha,
        "author": author,
        "date": date,
        "subject": subject,
        "body": body,
        "files": files_changed,
        "patch": patch,
        "patch_truncated": truncated,
    }


@tool
def git_show_file(repo_path: str, file_path: str, ref: str = "HEAD", max_lines: int = 400) -> dict:
    """Read a file from a git repository at a given ref."""
    logger.info(
        "Reading %s at %s in %s (max_lines=%s).",
        file_path,
        ref,
        repo_path,
        max_lines,
    )
    if max_lines <= 0:
        raise ValueError("max_lines must be > 0")

    spec = f"{ref}:{file_path}"
    cmd = ["git", "-C", repo_path, "show", spec]
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        error = (completed.stderr or "").strip() or "git show failed"
        logger.warning(
            "Failed to read %s at %s in %s: %s.",
            file_path,
            ref,
            repo_path,
            error,
        )
        return {"error": error}

    lines = completed.stdout.splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    logger.info("File content was truncated: %s.", truncated)
    return {
        "ref": ref,
        "path": file_path,
        "content": "\n".join(lines) + ("\n\n[file truncated]" if truncated else ""),
        "truncated": truncated,
    }


@tool
def git_grep(
    repo_path: str, pattern: str, max_matches: int = 50, fixed_string: bool = True
) -> list[dict]:
    """Search tracked files in a git repository (via `git grep`)."""
    pattern_preview = pattern if len(pattern) <= 120 else f"{pattern[:120]}..."
    logger.info(
        "Searching for %r in %s (fixed_string=%s, max_matches=%s).",
        pattern_preview,
        repo_path,
        fixed_string,
        max_matches,
    )
    if max_matches <= 0:
        raise ValueError("max_matches must be > 0")

    args = ["grep", "-n", "--full-name", "--no-color", "-I"]
    if fixed_string:
        args.append("-F")
    args.append(pattern)

    cmd = ["git", "-C", repo_path, *args]
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if completed.returncode == 1:
        return []
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "").strip() or "git grep failed")

    matches: list[dict] = []
    for line in completed.stdout.splitlines():
        # path:line:text
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, line_no, text = parts
        matches.append({"path": path, "line": int(line_no), "text": text})
        if len(matches) >= max_matches:
            break
    logger.info("Found %s matches.", len(matches))
    return matches


@tool
def git_diff(
    repo_path: str,
    ref_a: str,
    ref_b: str = "HEAD",
    max_lines: int = 400,
    path_filter: str = "",
) -> dict:
    """Compare two git refs and return the unified diff."""
    logger.info("Diffing %s..%s in %s (max_lines=%s).", ref_a, ref_b, repo_path, max_lines)
    if max_lines <= 0:
        raise ValueError("max_lines must be > 0")

    args = ["diff", "--no-color", f"{ref_a}...{ref_b}"]
    if path_filter:
        args += ["--", path_filter]

    out = _run_git(repo_path, args).stdout
    lines = out.splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    return {
        "ref_a": ref_a,
        "ref_b": ref_b,
        "diff": "\n".join(lines) + ("\n\n[diff truncated]" if truncated else ""),
        "truncated": truncated,
    }


@tool
def git_log_search(repo_path: str, pattern: str, max_count: int = 20) -> list[dict]:
    """Search commit messages in a git repository (via `git log --grep`)."""
    logger.info(
        "Searching commits for %r in %s (max_count=%s).",
        pattern,
        repo_path,
        max_count,
    )
    if max_count <= 0:
        raise ValueError("max_count must be > 0")

    fmt = "%H%x1f%s%x1f%ad%x1e"
    out = _run_git(
        repo_path,
        [
            "log",
            f"--grep={pattern}",
            "--all",
            f"--max-count={max_count}",
            "--date=iso-strict",
            f"--pretty=format:{fmt}",
        ],
    ).stdout

    results: list[dict] = []
    for record in out.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) != 3:
            continue
        sha, subject, date = parts
        results.append({"sha": sha, "subject": subject, "date": date})
    logger.info("Found %s matching commits.", len(results))
    return results


@tool
def git_ls_files(repo_path: str, path_prefix: str = "", max_files: int = 200) -> list[str]:
    """List tracked files in a git repository, optionally filtered by path prefix."""
    logger.info(
        "Listing files in %s (prefix=%r, max_files=%s).",
        repo_path,
        path_prefix,
        max_files,
    )
    if max_files <= 0:
        raise ValueError("max_files must be > 0")

    args = ["ls-files"]
    if path_prefix:
        args.append(path_prefix)

    out = _run_git(repo_path, args).stdout
    files: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        files.append(line)
        if len(files) >= max_files:
            break
    logger.info("Listed %s files.", len(files))
    return files


@tool
def ast_grep(
    repo_path: str,
    pattern: str,
    language: str = "",
    max_matches: int = 50,
) -> list[dict]:
    """Structural code search using ast-grep. Matches AST patterns instead of plain text."""
    pattern_preview = pattern if len(pattern) <= 120 else f"{pattern[:120]}..."
    logger.info(
        "ast-grep search for %r in %s (lang=%s, max_matches=%s).",
        pattern_preview,
        repo_path,
        language or "auto",
        max_matches,
    )
    if max_matches <= 0:
        raise ValueError("max_matches must be > 0")

    bin_path = shutil.which("ast-grep") or shutil.which("sg")
    if bin_path is None:
        return [{"error": "ast-grep is not installed (install via: cargo install ast-grep)"}]

    args = [bin_path, "--pattern", pattern, "--json"]
    if language:
        args += ["--lang", language]
    args += [repo_path]

    completed = subprocess.run(args, check=False, text=True, capture_output=True)
    if completed.returncode != 0 and not completed.stdout:
        error = (completed.stderr or "").strip() or "ast-grep failed"
        logger.warning("ast-grep failed: %s.", error)
        return [{"error": error}]

    import json

    try:
        raw: list[dict] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [{"error": "Failed to parse ast-grep JSON output"}]

    matches: list[dict] = []
    for item in raw:
        matches.append(
            {
                "file": item.get("file", ""),
                "line": item.get("range", {}).get("start", {}).get("line"),
                "text": item.get("text", ""),
            }
        )
        if len(matches) >= max_matches:
            break
    logger.info("ast-grep found %s matches.", len(matches))
    return matches
