from __future__ import annotations

import json
from pathlib import Path


def test_validator_reports_missing_sections(tmp_path: Path, cli) -> None:
    path = tmp_path / "implement_20260726_120001.md"
    path.write_text("# bad\n\n## 개발 목적\n누락\n", encoding="utf-8")
    result = cli("validate_dev_plan.py", path, "--format", "json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["valid"] is False
    assert any("Phase" in message for message in report["errors"])


def test_validator_rejects_wrong_filename(tmp_path: Path, cli) -> None:
    path = tmp_path / "plan.md"
    path.write_text("# plan\n", encoding="utf-8")
    assert cli("validate_dev_plan.py", path).returncode == 1
