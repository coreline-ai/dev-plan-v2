from __future__ import annotations

import json
from pathlib import Path


def create(tmp_path: Path, cli, stamp: str = "20260726_140000") -> Path:
    result = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "로그인 오류 수정",
        "--scope", "src/auth/session.py", "--exclude", "UI 변경", "--reference", "README.md",
        "--phase", "오류 처리", "--phase", "회귀 검증", "--test", "python3.11 -m unittest discover -s tests",
        "--timestamp", stamp, "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["path"])


def test_creates_v1_plus_plan_without_overwriting(tmp_path: Path, cli) -> None:
    plan = create(tmp_path, cli)
    text = plan.read_text(encoding="utf-8")
    for heading in (
        "개발 목적", "개발 범위", "제외 범위", "참조 문서", "공통 진행 규칙",
        "실행 상태 및 모델 라우팅", "Phase 상태 요약", "QA 관점", "최종 결과 요약",
    ):
        assert f"## {heading}" in text
    assert "## Phase 1. 오류 처리" in text
    assert "## Phase 2. 회귀 검증" in text
    assert "### 자체 테스트" in text
    assert cli("validate_dev_plan.py", plan).returncode == 0

    before = plan.read_bytes()
    collision = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "다시 생성", "--timestamp", "20260726_140000",
    )
    assert collision.returncode == 2
    assert plan.read_bytes() == before


def test_ready_validation_requires_resolved_execution_details(tmp_path: Path, cli) -> None:
    plan = create(tmp_path, cli, "20260726_140001")
    assert cli("validate_dev_plan.py", plan, "--ready").returncode == 1

    text = plan.read_text(encoding="utf-8")
    replacements = {
        "- 계획 상태: DRAFT": "- 계획 상태: READY",
        "- Lead: 실행 전 실제 Sol 모델 기록 (reasoning: high)": "- Lead: gpt-5.6-sol (reasoning: high)",
        "- ROUTINE Worker: 실행 전 실제 Terra 모델 기록 (reasoning: medium)": "- ROUTINE Worker: gpt-5.6-terra (reasoning: medium)",
        "- COMPLEX Worker: 실행 전 실제 Luna 모델 확인; 없으면 BLOCKED 또는 재분해 (reasoning: high)": "- COMPLEX Worker: gpt-5.6-luna 또는 BLOCKED (reasoning: high)",
        "- Independent QA: 새 Sol 컨텍스트로 실행 전 실제 모델 기록 (reasoning: high)": "- Independent QA: gpt-5.6-sol 새 컨텍스트 (reasoning: high)",
        "- 마지막 확인: 미실행": "- 마지막 확인: 2026-07-26 모델 확인",
        "- 실행한 테스트: 미실행": "- 실행한 테스트: 테스트 명령 등록",
        "- QA 판정: 미실행": "- QA 판정: 실행 전",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    plan.write_text(text, encoding="utf-8")
    assert cli("validate_dev_plan.py", plan, "--ready").returncode == 0
