from __future__ import annotations

from pathlib import Path

from test_parallel_dev_plan import create_plan


def test_validator_rejects_overlapping_workstream_paths(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli)
    text = plan.read_text(encoding="utf-8").replace("`src/web/`, `tests/web/`", "`src/api/`", 1)
    plan.write_text(text, encoding="utf-8")
    result = cli("validate_parallel_dev_plan.py", plan, "--format", "json")
    assert result.returncode == 1
    assert "겹칩니다" in result.stdout


def test_validator_rejects_missing_or_wrong_wave_assignment(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260726_160101")
    text = plan.read_text(encoding="utf-8").replace("- Wave 0: COMMON\n", "")
    plan.write_text(text, encoding="utf-8")
    result = cli("validate_parallel_dev_plan.py", plan, "--format", "json")
    assert result.returncode == 1
    assert "Wave" in result.stdout

    plan = create_plan(tmp_path, cli, "20260726_160102")
    text = plan.read_text(encoding="utf-8").replace("- Wave 2: INTEGRATION", "- Wave 1: INTEGRATION")
    plan.write_text(text, encoding="utf-8")
    result = cli("validate_parallel_dev_plan.py", plan, "--format", "json")
    assert result.returncode == 1
    assert "INTEGRATION" in result.stdout


def test_validator_allows_optional_execution_record_without_claiming_success(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260726_160103", common=False)
    text = plan.read_text(encoding="utf-8")
    assert "- Wave 1: WS-01, WS-02" in text
    assert "- Wave 2: INTEGRATION" in text
    plan.write_text(text + "\n## 실행 기록\n- 시작 시각: 미실행\n", encoding="utf-8")
    assert cli("validate_parallel_dev_plan.py", plan).returncode == 0


def test_validator_rejects_wrong_filename(tmp_path: Path, cli) -> None:
    path = tmp_path / "plan.md"
    path.write_text("# plan.md\n", encoding="utf-8")
    assert cli("validate_parallel_dev_plan.py", path).returncode == 1
