from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill_keeps_v1_as_common_owner_and_v2_plan_immutable() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "V1 `dev-plan-generator`의 공통 Dev Lesson 도구" in skill
    assert "LESSON_TOOL_UNAVAILABLE" in skill
    assert "Worker가 공유 문서에 쓰지 않고" in skill
    assert "생성된 plan JSON/Markdown과 ledger hash는 수정하지 않는다" in skill
    assert "parallel_*.outcomes.json" in skill


def test_adapter_requires_lead_only_post_qa_triage() -> None:
    adapter = (ROOT / "references/dev-lesson-adapter.md").read_text(encoding="utf-8")
    assert "Worker는 `docs/dev-lessons/`를 수정하지 않는다" in adapter
    assert "통합·QA 후" in adapter
    assert "plan-only | existing-reference | new-lesson" in adapter
    assert "MVP에서는 plan 역링크, ledger `lesson_ids`, occurrence append를 추가하지 않는다" in adapter
    assert "record-pending" in adapter


def test_parallel_format_reuses_existing_references_without_schema_change() -> None:
    plan_format = (ROOT / "references/parallel-plan-format.md").read_text(encoding="utf-8")
    assert "기존 `references` 문자열" in plan_format
    assert "Lesson 전용 schema 필드는 추가하지 않는다" in plan_format
    assert "생성된 JSON이나 Markdown을 수정하면 안 된다" in plan_format


def test_v1_v2_trigger_and_separate_install_contract_is_explicit() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    assert "병렬화 가능한지 판단" in frontmatter
    assert "계획 세워줘" in frontmatter
    assert "V1과 V2는 별도 패키지" in skill
    assert "V2는 V1을 내장하거나 자동 설치하지 않는다" in skill
    assert "$parallel-dev-plan-orchestrator only for this explicit 병렬 개발 계획 request" in metadata
    assert "V1과 V2는 별도 설치" in readme
