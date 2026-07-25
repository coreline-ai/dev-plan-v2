from __future__ import annotations

import json
from pathlib import Path


def test_validator_reports_missing_sections(tmp_path: Path, cli) -> None:
    path = tmp_path / "implement_20260726_140002.md"
    path.write_text("# implement_20260726_140002.md\n\n작성 일시: `2026-07-26`\n\n## 개발 목적\n누락\n", encoding="utf-8")
    result = cli("validate_dev_plan.py", path, "--format", "json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["valid"] is False
    assert any("Phase" in message for message in report["errors"])


def test_validator_rejects_phase_summary_mismatch(tmp_path: Path, cli) -> None:
    path = tmp_path / "dev-plan" / "implement_20260726_140003.md"
    generated = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "기능", "--scope", "src/app.py",
        "--phase", "구현", "--phase", "검증", "--test", "python3.11 -m unittest", "--timestamp", "20260726_140003",
    )
    assert generated.returncode == 0
    text = path.read_text(encoding="utf-8").replace("- [ ] Phase 2 완료 — 검증\n", "")
    path.write_text(text, encoding="utf-8")
    result = cli("validate_dev_plan.py", path, "--format", "json")
    assert result.returncode == 1
    assert any("Phase 상태 요약" in message for message in json.loads(result.stdout)["errors"])


def test_validator_rejects_wrong_filename(tmp_path: Path, cli) -> None:
    path = tmp_path / "plan.md"
    path.write_text("# plan\n", encoding="utf-8")
    assert cli("validate_dev_plan.py", path).returncode == 1
