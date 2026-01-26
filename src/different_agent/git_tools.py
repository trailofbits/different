from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


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
    logger.debug("git command repo=%s args=%s", repo_path, args)
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
        "git_recent_commits repo=%s since_days=%s max_count=%s",
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
    logger.info("git_recent_commits result_count=%s", len(commits))
    return commits


@tool
def git_show_commit(repo_path: str, sha: str, max_patch_lines: int = 400) -> dict:
    """Return commit metadata + file list + a truncated patch."""
    logger.info(
        "git_show_commit repo=%s sha=%s max_patch_lines=%s",
        repo_path,
        sha,
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
        "git_show_commit files=%s patch_truncated=%s",
        len(files_changed),
        truncated,
    )
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
        "git_show_file repo=%s path=%s ref=%s max_lines=%s",
        repo_path,
        file_path,
        ref,
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
            "git_show_file failed repo=%s path=%s ref=%s error=%s",
            repo_path,
            file_path,
            ref,
            error,
        )
        return {"error": error}

    lines = completed.stdout.splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    logger.info("git_show_file truncated=%s", truncated)
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
        "git_grep repo=%s pattern=%r fixed_string=%s max_matches=%s",
        repo_path,
        pattern_preview,
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
    logger.info("git_grep result_count=%s", len(matches))
    return matches
