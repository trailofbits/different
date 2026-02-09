from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from different_agent import git_tools


def _git(repo: Path, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    assert git is not None
    import os

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(
        [git, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
        **kwargs,  # type: ignore[arg-type]
    )


def _add_commit(repo: Path, filename: str, content: str, message: str) -> str:
    """Helper: write a file, commit it, return the sha."""
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, ["add", filename])
    _git(repo, ["commit", "-m", message])
    out = _git(repo, ["rev-parse", "HEAD"], text=True)
    return out.stdout.strip()


def test_git_recent_commits_returns_commits(git_repo: Path) -> None:
    commits = git_tools.git_recent_commits.invoke(
        {"repo_path": str(git_repo), "since_days": 1, "max_count": 5}
    )
    assert commits
    assert {"sha", "author", "date", "subject"}.issubset(commits[0].keys())


def test_git_show_commit_truncates_patch(git_repo: Path) -> None:
    commits = git_tools.git_recent_commits.invoke(
        {"repo_path": str(git_repo), "since_days": 1, "max_count": 1}
    )
    sha = commits[0]["sha"]
    git_tools.reset_analyzed_commit_count()
    result = git_tools.git_show_commit.invoke(
        {"repo_path": str(git_repo), "sha": sha, "max_patch_lines": 1}
    )
    assert result["patch_truncated"] is True
    assert "[patch truncated]" in result["patch"]
    assert git_tools.get_analyzed_commit_count() == 1


def test_git_show_file_and_grep(git_repo: Path) -> None:
    content = git_tools.git_show_file.invoke(
        {"repo_path": str(git_repo), "file_path": "file.txt", "max_lines": 1}
    )
    assert content["truncated"] is True
    assert "[file truncated]" in content["content"]

    missing = git_tools.git_show_file.invoke(
        {"repo_path": str(git_repo), "file_path": "missing.txt"}
    )
    assert "error" in missing

    matches = git_tools.git_grep.invoke({"repo_path": str(git_repo), "pattern": "line2"})
    assert matches
    assert matches[0]["path"] == "file.txt"

    no_matches = git_tools.git_grep.invoke({"repo_path": str(git_repo), "pattern": "nope"})
    assert no_matches == []


def test_git_recent_commits_requires_repo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Not a git repo"):
        git_tools.git_recent_commits.invoke(
            {"repo_path": str(tmp_path / "not_repo"), "since_days": 1, "max_count": 1}
        )


def test_git_diff_shows_changes(git_repo: Path) -> None:
    # Get the initial commit sha
    commits = git_tools.git_recent_commits.invoke(
        {"repo_path": str(git_repo), "since_days": 1, "max_count": 1}
    )
    initial_sha = commits[0]["sha"]

    # Create a second commit with changes
    _add_commit(git_repo, "file.txt", "line1\nchanged\nline3\n", "fix: update line2")

    result = git_tools.git_diff.invoke(
        {"repo_path": str(git_repo), "ref_a": initial_sha, "ref_b": "HEAD"}
    )
    assert "changed" in result["diff"]
    assert result["ref_a"] == initial_sha
    assert result["ref_b"] == "HEAD"
    assert result["truncated"] is False


def test_git_diff_truncates(git_repo: Path) -> None:
    commits = git_tools.git_recent_commits.invoke(
        {"repo_path": str(git_repo), "since_days": 1, "max_count": 1}
    )
    initial_sha = commits[0]["sha"]
    _add_commit(git_repo, "file.txt", "line1\nchanged\nline3\n", "fix: change")

    result = git_tools.git_diff.invoke(
        {"repo_path": str(git_repo), "ref_a": initial_sha, "ref_b": "HEAD", "max_lines": 1}
    )
    assert result["truncated"] is True
    assert "[diff truncated]" in result["diff"]


def test_ast_grep_missing_binary(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = git_tools.ast_grep.invoke({"repo_path": str(git_repo), "pattern": "line1"})
    assert result
    assert "error" in result[0]
    assert "not installed" in result[0]["error"]
