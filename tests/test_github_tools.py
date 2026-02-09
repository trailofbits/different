from __future__ import annotations

import urllib.error
import urllib.request

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

    monkeypatch.setattr(gh, "_run_git", lambda _repo_path, _args: DummyResult)
    assert gh.git_github_repo.invoke({"repo_path": "/home/test/repo"}) == {
        "owner": "acme",
        "repo": "widgets",
    }


def test_git_github_repo_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_repo_path: str, _args: list[str]) -> None:
        raise RuntimeError("no remote")

    monkeypatch.setattr(gh, "_run_git", boom)
    result = gh.git_github_repo.invoke({"repo_path": "/home/test/repo"})
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


def test_github_request_json_sets_auth_header_and_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "fake-token")

    seen: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req: urllib.request.Request, timeout: int):  # noqa: ARG001
        seen["auth"] = req.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    assert gh._github_request_json("https://api.github.com/test") == {"ok": True}
    assert seen["auth"] == "Bearer fake-token"


def test_record_analyzed_pr_ignores_invalid_inputs() -> None:
    gh.reset_analyzed_pr_count()
    gh._record_analyzed_pr(None, "repo", 1)
    gh._record_analyzed_pr("owner", "", 1)
    gh._record_analyzed_pr("owner", "repo", None)
    assert gh.get_analyzed_pr_count() == 0


def test_parse_github_repo_from_remote_empty() -> None:
    assert gh._parse_github_repo_from_remote("   ") is None


def test_git_github_repo_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResult:
        stdout = "https://gitlab.com/acme/widgets"

    monkeypatch.setattr(gh, "_run_git", lambda _repo_path, _args: DummyResult)
    result = gh.git_github_repo.invoke({"repo_path": "/home/test/repo"})
    assert "error" in result


def test_github_recent_prs_non_range_filters_by_since_days(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(_url: str) -> list[dict]:
        return [
            {
                "number": 1,
                "title": "Old PR",
                "state": "closed",
                "merged_at": None,
                "updated_at": "1970-01-01T00:00:00Z",
                "html_url": "https://example.com/1",
            },
            {
                "number": 2,
                "title": "New PR",
                "state": "closed",
                "merged_at": None,
                "updated_at": "2999-01-01T00:00:00Z",
                "html_url": "https://example.com/2",
            },
            {
                "number": 3,
                "title": "No date",
                "state": "closed",
                "merged_at": None,
                "updated_at": None,
                "html_url": "https://example.com/3",
            },
        ]

    gh.reset_analyzed_pr_count()
    monkeypatch.setattr(gh, "_github_request_json", fake_request)
    results = gh.github_recent_prs.invoke(
        {"owner": "acme", "repo": "widgets", "since_days": 1, "max_count": 10}
    )
    assert [item["number"] for item in results] == [2, 3]
    assert gh.get_analyzed_pr_count() == 2


def test_github_recent_issues_error_non_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh, "_github_request_json", lambda _url: {"nope": True})
    results = gh.github_recent_issues.invoke({"owner": "acme", "repo": "widgets"})
    assert results[0]["error"] == "Unexpected response from GitHub issues API"


def test_github_recent_issues_error_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_url: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(gh, "_github_request_json", boom)
    results = gh.github_recent_issues.invoke({"owner": "acme", "repo": "widgets"})
    assert "error" in results[0]


def test_github_fetch_issue_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def ok(_url: str) -> dict:
        return {
            "number": 123,
            "title": "Issue",
            "state": "closed",
            "labels": [{"name": "bug"}],
            "closed_at": None,
            "updated_at": None,
            "html_url": "https://example.com",
            "body": "x" * 13000,
        }

    monkeypatch.setattr(gh, "_github_request_json", ok)
    issue = gh.github_fetch_issue.invoke({"owner": "acme", "repo": "widgets", "number": 123})
    assert issue["number"] == 123
    assert issue["labels"] == ["bug"]
    assert len(issue["body"]) == 12000

    monkeypatch.setattr(gh, "_github_request_json", lambda _url: ["nope"])
    error = gh.github_fetch_issue.invoke({"owner": "acme", "repo": "widgets", "number": 1})
    assert "error" in error


def test_github_fetch_pr_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh,
        "_github_request_json",
        lambda _url: {
            "number": 12,
            "title": "PR",
            "state": "closed",
            "labels": [{"name": "bug"}, {"name": "security"}],
            "merged_at": None,
            "updated_at": None,
            "html_url": "https://example.com",
            "body": "x" * 13000,
        },
    )
    pr = gh.github_fetch_pr.invoke({"owner": "acme", "repo": "widgets", "number": 12})
    assert pr["number"] == 12
    assert pr["labels"] == ["bug", "security"]
    assert len(pr["body"]) == 12000

    monkeypatch.setattr(gh, "_github_request_json", lambda _url: ["nope"])
    error = gh.github_fetch_pr.invoke({"owner": "acme", "repo": "widgets", "number": 12})
    assert "error" in error


def test_github_fetch_pr_files_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_url: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(gh, "_github_request_json", boom)
    results = gh.github_fetch_pr_files.invoke({"owner": "acme", "repo": "widgets", "number": 12})
    assert "error" in results[0]


def test_github_fetch_pr_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url: str) -> list[dict]:
        if "/pulls/" in url and "/comments" in url:
            return [
                {
                    "user": {"login": "alice"},
                    "body": "review comment " + "x" * 5000,
                    "created_at": "2024-01-01T00:00:00Z",
                    "path": "src/main.py",
                    "line": 42,
                },
            ]
        return [
            {
                "user": {"login": "bob"},
                "body": "issue comment",
                "created_at": "2024-01-02T00:00:00Z",
            },
        ]

    monkeypatch.setattr(gh, "_github_request_json", fake_request)
    comments = gh.github_fetch_pr_comments.invoke(
        {"owner": "acme", "repo": "widgets", "number": 10}
    )
    assert len(comments) == 2
    assert comments[0]["user"] == "alice"
    assert comments[0]["path"] == "src/main.py"
    assert comments[0]["line"] == 42
    assert len(comments[0]["body"]) == 4000  # truncated
    assert comments[1]["user"] == "bob"
    assert comments[1]["path"] is None
    assert comments[1]["line"] is None


def test_github_fetch_pr_comments_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_url: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(gh, "_github_request_json", boom)
    result = gh.github_fetch_pr_comments.invoke({"owner": "acme", "repo": "widgets", "number": 10})
    assert "error" in result[0]
