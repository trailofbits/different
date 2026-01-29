from __future__ import annotations

from different_agent.report import render_findings_html, render_target_assessment_html


def test_render_findings_html_escapes_values() -> None:
    findings = [
        {
            "id": "<f-1>",
            "kind": "bug",
            "severity": "high",
            "title": "Title & stuff",
            "root_cause": "a < b",
            "fix_summary": "use & sanitize",
        }
    ]
    html = render_findings_html(findings)
    assert "Findings" in html
    assert "&lt;f-1&gt;" in html
    assert "Title &amp; stuff" in html
    assert "a &lt; b" in html
    assert "use &amp; sanitize" in html


def test_render_target_assessment_html_escapes_values() -> None:
    assessments = [
        {
            "finding_id": "F&1",
            "applies": True,
            "confidence": 0.75,
            "why": "<because>",
        }
    ]
    html = render_target_assessment_html(assessments)
    assert "Target Assessment" in html
    assert "F&amp;1" in html
    assert "&lt;because&gt;" in html
