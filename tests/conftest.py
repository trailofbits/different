from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Test User")
    env.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Test User")
    env.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
    return env


def _run_git(repo_path: Path, args: list[str]) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        text=True,
        capture_output=True,
        env=_git_env(),
    )


def init_git_repo(repo_path: Path) -> Path:
    repo_path.mkdir(parents=True, exist_ok=True)
    _run_git(repo_path, ["init"])
    (repo_path / "file.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    _run_git(repo_path, ["add", "file.txt"])
    _run_git(repo_path, ["commit", "-m", "initial"])
    return repo_path


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    return init_git_repo(tmp_path / "repo")


@pytest.fixture()
def make_git_repo(tmp_path: Path):
    def _make(name: str) -> Path:
        return init_git_repo(tmp_path / name)

    return _make


def _require_skip_reason(marker: pytest.Mark, item: pytest.Item) -> None:
    reason = marker.kwargs.get("reason") if marker.kwargs else None
    if not reason and marker.args:
        reason = marker.args[0] if isinstance(marker.args[0], str) else None
    if not reason:
        raise pytest.UsageError(f"Skip markers must include a reason: {item.nodeid}")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        for marker in item.iter_markers(name="skip"):
            _require_skip_reason(marker, item)
        for marker in item.iter_markers(name="skipif"):
            _require_skip_reason(marker, item)
