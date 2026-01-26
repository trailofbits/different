from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from different_agent import cli


class DummyUsage:
    def __init__(self) -> None:
        self.usage_metadata: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyStructured:
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self) -> dict:
        return self._data


class StubAgent:
    def __init__(self, result: dict):
        self._result = result

    def invoke(self, _payload: dict):
        return self._result


def _patch_main_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    extract_result: dict,
    target_result: dict | None = None,
) -> None:
    class DummyResolved:
        def __init__(self):
            self.model = object()
            self.provider = "openai"
            self.name = "gpt-5.2"

    monkeypatch.setattr(cli, "get_usage_metadata_callback", lambda: DummyUsage())
    monkeypatch.setattr(cli, "create_chat_model", lambda **_kw: DummyResolved())
    monkeypatch.setattr(
        cli, "create_inspiration_agent", lambda *_a, **_k: StubAgent(extract_result)
    )
    if target_result is not None:
        monkeypatch.setattr(cli, "create_target_agent", lambda *_a, **_k: StubAgent(target_result))


def test_main_extract_only_writes_findings(
    make_git_repo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = make_git_repo("inspiration")
    findings = [
        {
            "id": "F-1",
            "kind": "bug",
            "severity": "low",
            "title": "Sample",
            "root_cause": "Root",
            "fix_summary": "Fix",
            "evidence": {"commits": [], "files_changed": [], "diff_snippets": [], "links": []},
            "tags": [],
        }
    ]
    extract_result = {"structured_response": DummyStructured({"findings": findings})}
    _patch_main_dependencies(monkeypatch, extract_result)
    monkeypatch.setattr(cli, "_output_suffix", lambda *_: "01-01_00-00")

    base_path = tmp_path / "findings.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "different-agent",
            "--extract-only",
            "--inspiration",
            str(repo),
            "--findings-out",
            str(base_path),
        ],
    )

    assert cli.main() == 0
    output_path = tmp_path / "inspiration" / "findings_01-01_00-00.json"
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data[0]["id"] == "F-1"


def test_main_full_run_falls_back_to_state_files(
    make_git_repo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inspiration = make_git_repo("inspiration")
    target = make_git_repo("target")

    findings_json = json.dumps(
        [
            {
                "id": "F-2",
                "kind": "bug",
                "severity": "medium",
                "title": "Sample",
                "root_cause": "Root",
                "fix_summary": "Fix",
                "evidence": {"commits": [], "files_changed": [], "diff_snippets": [], "links": []},
                "tags": [],
            }
        ]
    )
    assessments_json = json.dumps(
        [
            {
                "finding_id": "F-2",
                "applies": False,
                "confidence": 0.9,
                "why": "Not applicable false positive",
                "evidence": {},
                "suggested_next_steps": [],
            }
        ]
    )
    extract_result = {"files": {"/outputs/findings.json": {"content": findings_json.splitlines()}}}
    target_result = {
        "files": {"/outputs/target_assessment.json": {"content": assessments_json.splitlines()}}
    }

    _patch_main_dependencies(monkeypatch, extract_result, target_result)
    monkeypatch.setattr(cli, "_output_suffix", lambda *_: "01-01_00-00")

    findings_path = tmp_path / "findings.json"
    assessment_path = tmp_path / "assessment.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "different-agent",
            "--inspiration",
            str(inspiration),
            "--target",
            str(target),
            "--findings-out",
            str(findings_path),
            "--assessment-out",
            str(assessment_path),
        ],
    )

    assert cli.main() == 0
    output_findings = tmp_path / "target" / "findings_01-01_00-00.json"
    output_assessment = tmp_path / "target" / "assessment_01-01_00-00.json"
    assert json.loads(output_findings.read_text(encoding="utf-8"))[0]["id"] == "F-2"
    assert json.loads(output_assessment.read_text(encoding="utf-8"))[0]["finding_id"] == "F-2"
