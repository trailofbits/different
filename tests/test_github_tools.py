from __future__ import annotations

import urllib.error

import pytest

from different_agent import github_tools as gh


def test_parse_github_repo_from_remote() -> None:
    ssh = gh._parse_github_repo_from_remote("git@github.com:owner/repo.git")
    assert ssh is not None
    assert ssh.owner == "owner"
    assert ssh.repo == "repo"

    https = gh._parse_github_repo_from_remote("https://github.com/acme/widgets")
    assert https is not None
    assert https.owner == "acme"
    assert https.repo == "widgets"

    assert gh._parse_github_repo_from_remote("https://gitlab.com/acme/widgets") is None


def test_iso_since_days_format() -> None:
    value = gh._iso_since_days(1)
    assert value.endswith("+00:00")
    assert "." not in value


def test_git_github_repo_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResult:
        stdout = "git@github.com:acme/widgets.git"

    monkeypatch.setattr(gh, "_run_git", lambda repo_path, args: DummyResult)
    assert gh.git_github_repo.invoke({"repo_path": "/tmp/repo"}) == {
        "owner": "acme",
        "repo": "widgets",
    }


def test_git_github_repo_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_repo_path: str, _args: list[str]) -> None:
        raise RuntimeError("no remote")

    monkeypatch.setattr(gh, "_run_git", boom)
    result = gh.git_github_repo.invoke({"repo_path": "/tmp/repo"})
    assert "error" in result


def test_github_recent_prs_range(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url: str) -> dict:
        number = int(url.rsplit("/", 1)[1])
        return {
            "number": number,
            "title": f"PR {number}",
            "state": "closed",
            "merged_at": None,
            "updated_at": "2024-01-01T00:00:00Z",
            "html_url": "https://example.com",
        }

    gh.reset_analyzed_pr_count()
    monkeypatch.setattr(gh, "_github_request_json", fake_request)
    results = gh.github_recent_prs.invoke(
        {"owner": "acme", "repo": "widgets", "from_pr": 1, "to_pr": 2}
    )
    assert [item["number"] for item in results] == [1, 2]
    assert gh.get_analyzed_pr_count() == 2


def test_github_recent_prs_range_errors() -> None:
    results = gh.github_recent_prs.invoke(
        {"owner": "acme", "repo": "widgets", "from_pr": 2, "to_pr": 1}
    )
    assert results[0]["error"] == "from_pr must be <= to_pr"


def test_github_recent_issues_filters_prs(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(_url: str) -> list[dict]:
        return [
            {"number": 1, "title": "Issue", "state": "closed", "labels": []},
            {"number": 2, "pull_request": {}, "state": "closed"},
        ]

    monkeypatch.setattr(gh, "_github_request_json", fake_request)
    results = gh.github_recent_issues.invoke({"owner": "acme", "repo": "widgets"})
    assert len(results) == 1
    assert results[0]["number"] == 1


def test_github_fetch_pr_files_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        [
            {
                "filename": "file.py",
                "status": "modified",
                "additions": 1,
                "deletions": 0,
                "changes": 1,
                "patch": "diff",
            }
        ],
        [],
    ]

    def fake_request(_url: str):
        return responses.pop(0)

    gh.reset_analyzed_pr_count()
    monkeypatch.setattr(gh, "_github_request_json", fake_request)
    files = gh.github_fetch_pr_files.invoke(
        {"owner": "acme", "repo": "widgets", "number": 12, "max_files": 5}
    )
    assert files[0]["filename"] == "file.py"
    assert gh.get_analyzed_pr_count() == 1


def test_github_recent_prs_skips_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url: str):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    monkeypatch.setattr(gh, "_github_request_json", fake_request)
    results = gh.github_recent_prs.invoke(
        {"owner": "acme", "repo": "widgets", "from_pr": 1, "to_pr": 1}
    )
    assert results == []
