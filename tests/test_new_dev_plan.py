from __future__ import annotations

import json
from pathlib import Path


RUNTIME_ALL = "gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna"


def create(tmp_path: Path, cli, stamp: str = "20260726_140000") -> Path:
    result = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "로그인 오류 수정",
        "--scope", "src/auth/session.py", "--exclude", "UI 변경", "--reference", "README.md",
        "--phase", "오류 처리", "--phase", "회귀 검증", "--test", "python3.11 -m unittest discover -s tests",
        "--timestamp", stamp, "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["path"])


def ready_text(text: str, runtime: str = RUNTIME_ALL) -> str:
    replacements = {
        "- 계획 상태: DRAFT": "- 계획 상태: READY",
        "- 확인된 런타임 모델: UNVERIFIED": f"- 확인된 런타임 모델: {runtime}",
        "- Lead requested model: UNASSIGNED (Sol)": "- Lead requested model: gpt-5.6-sol",
        "- QA requested model: UNASSIGNED (Sol, fresh)": "- QA requested model: gpt-5.6-sol",
        "- requested model: UNASSIGNED (Terra)": "- requested model: gpt-5.6-terra",
        "- requested model: UNASSIGNED (Luna)": "- requested model: gpt-5.6-luna",
        "- 마지막 확인: 미실행": "- 마지막 확인: 2026-07-26 모델 preflight 확인",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def test_creates_v1_plus_plan_without_overwriting(tmp_path: Path, cli) -> None:
    plan = create(tmp_path, cli)
    text = plan.read_text(encoding="utf-8")
    for heading in (
        "개발 목적", "개발 범위", "제외 범위", "참조 문서", "공통 진행 규칙",
        "실행 상태 및 모델 라우팅", "Phase 상태 요약", "QA 관점", "실행 기록",
    ):
        assert f"## {heading}" in text
    assert "## Phase 1. 오류 처리" in text
    assert "## Phase 2. 회귀 검증" in text
    assert "### Worker 배정" in text
    assert "- 작업 등급: ROUTINE" in text
    assert "- context: fork_turns: none" in text
    assert cli("validate_dev_plan.py", plan).returncode == 0

    before = plan.read_bytes()
    collision = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "다시 생성", "--timestamp", "20260726_140000",
    )
    assert collision.returncode == 2
    assert plan.read_bytes() == before


def test_ready_validation_requires_exact_listed_model_assignments(tmp_path: Path, cli) -> None:
    plan = create(tmp_path, cli, "20260726_140001")
    assert cli("validate_dev_plan.py", plan, "--ready").returncode == 1

    plan.write_text(ready_text(plan.read_text(encoding="utf-8")), encoding="utf-8")
    assert cli("validate_dev_plan.py", plan, "--ready").returncode == 0

    text = plan.read_text(encoding="utf-8").replace(
        "- Lead requested model: gpt-5.6-sol", "- Lead requested model: gpt-5.5-sol"
    )
    plan.write_text(text, encoding="utf-8")
    assert cli("validate_dev_plan.py", plan, "--ready").returncode == 1


def test_ready_rejects_complex_phase_when_luna_is_unavailable(tmp_path: Path, cli) -> None:
    result = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "복잡 기능",
        "--scope", "src/complex.py", "--phase", "복잡 구현", "--complex-phase", "복잡 구현",
        "--test", "python3.11 -m unittest", "--timestamp", "20260726_140002", "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    plan = Path(json.loads(result.stdout)["path"])
    plan.write_text(ready_text(plan.read_text(encoding="utf-8"), "gpt-5.6-sol, gpt-5.6-terra"), encoding="utf-8")

    check = cli("validate_dev_plan.py", plan, "--ready", "--format", "json")
    assert check.returncode == 1
    assert any("Luna" in error for error in json.loads(check.stdout)["errors"])


def test_complete_requires_host_actual_models_to_match_requested(tmp_path: Path, cli) -> None:
    plan = create(tmp_path, cli, "20260726_140003")
    text = ready_text(plan.read_text(encoding="utf-8"))
    replacements = {
        "- 계획 상태: READY": "- 계획 상태: DONE",
        "- Lead actual model: PENDING": "- Lead actual model: gpt-5.6-sol",
        "- QA actual model: PENDING": "- QA actual model: gpt-5.6-sol",
        "- actual model: PENDING": "- actual model: gpt-5.6-terra",
        "- QA verdict: PENDING": "- QA verdict: PASS",
        "- 실행한 테스트: 미실행": "- 실행한 테스트: python3.11 -m unittest discover -s tests (PASS)",
        "- Worker 보고: 미실행": "- Worker 보고: 두 Phase 완료, diff와 테스트 보고됨",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    plan.write_text(text.replace("- [ ]", "- [x]"), encoding="utf-8")
    assert cli("validate_dev_plan.py", plan, "--complete").returncode == 0

    mismatch = plan.read_text(encoding="utf-8").replace(
        "- actual model: gpt-5.6-terra", "- actual model: gpt-5.7-terra", 1
    )
    plan.write_text(mismatch, encoding="utf-8")
    assert cli("validate_dev_plan.py", plan, "--complete").returncode == 1
