from __future__ import annotations

from pathlib import Path

import pytest

from different_agent import git_tools


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
