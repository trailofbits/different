from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return
    details = "\n".join(
        [
            f"command: {' '.join(cmd)}",
            f"exit_code: {result.returncode}",
            f"stdout:\n{result.stdout}",
            f"stderr:\n{result.stderr}",
        ]
    ).strip()
    raise AssertionError(details)


def test_tooling_smoke() -> None:
    _run(["ruff", "format", "--check", "."])
    _run(["ruff", "check", "."])
    _run(["ty", "check", "src/"])
