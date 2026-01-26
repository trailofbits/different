from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any


def _safe_json(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return html.escape(str(value))
    return html.escape(str(value))


def render_findings_html(findings: list[dict]) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows = []
    for f in findings:
        rows.append(
            "<tr>"
            f"<td>{_safe_json(f.get('id'))}</td>"
            f"<td>{_safe_json(f.get('kind'))}</td>"
            f"<td>{_safe_json(f.get('severity'))}</td>"
            f"<td>{_safe_json(f.get('title'))}</td>"
            f"<td><pre>{_safe_json(f.get('root_cause'))}</pre></td>"
            f"<td><pre>{_safe_json(f.get('fix_summary'))}</pre></td>"
            "</tr>"
        )

    table = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Different Agent – Findings</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; }}
      h1 {{ margin: 0 0 8px; }}
      .meta {{ color: #666; margin: 0 0 16px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
      th {{ background: #f7f7f7; text-align: left; }}
      pre {{ white-space: pre-wrap; margin: 0; }}
      code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>Findings</h1>
    <p class="meta">Generated at <code>{html.escape(now)}</code></p>
    <table>
      <thead>
        <tr>
          <th>id</th>
          <th>kind</th>
          <th>severity</th>
          <th>title</th>
          <th>root_cause</th>
          <th>fix_summary</th>
        </tr>
      </thead>
      <tbody>
        {table}
      </tbody>
    </table>
  </body>
</html>
"""


def render_target_assessment_html(assessments: list[dict]) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows = []
    for a in assessments:
        rows.append(
            "<tr>"
            f"<td>{_safe_json(a.get('finding_id'))}</td>"
            f"<td>{_safe_json(a.get('applies'))}</td>"
            f"<td>{_safe_json(a.get('confidence'))}</td>"
            f"<td><pre>{_safe_json(a.get('why'))}</pre></td>"
            "</tr>"
        )

    table = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Different Agent – Target Assessment</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; }}
      h1 {{ margin: 0 0 8px; }}
      .meta {{ color: #666; margin: 0 0 16px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
      th {{ background: #f7f7f7; text-align: left; }}
      pre {{ white-space: pre-wrap; margin: 0; }}
      code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>Target Assessment</h1>
    <p class="meta">Generated at <code>{html.escape(now)}</code></p>
    <table>
      <thead>
        <tr>
          <th>finding_id</th>
          <th>applies</th>
          <th>confidence</th>
          <th>why</th>
        </tr>
      </thead>
      <tbody>
        {table}
      </tbody>
    </table>
  </body>
</html>
"""
