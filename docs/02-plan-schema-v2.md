# v2 계획 스키마 안내

최종 갱신: `2026-07-25 KST`

## 정본

런타임 스키마의 단일 정본은
[`references/plan-schema-v2.md`](../references/plan-schema-v2.md)다.

이 문서는 중복 규격을 보관하지 않는다. 스키마·상태·이벤트·evidence 규칙을 바꿀
때는 정본을 먼저 수정하고 다음 구현과 테스트를 함께 갱신한다.

- 파서·serializer·검증기: `scripts/plan_core.py`
- 생성기: `scripts/new_dev_plan.py`
- v1 변환기: `scripts/upgrade_dev_plan.py`
- 검증 CLI: `scripts/validate_dev_plan.py`
- 상태 이벤트 CLI: `scripts/update_plan_state.py`
- 회귀 테스트: `tests/test_validate_dev_plan.py`,
  `tests/test_update_plan_state.py`

## 구현된 핵심 계약

- `codex-dev-plan/v2` frontmatter와 고정 섹션 순서
- Phase/DEV/TEST/QA 고유 ID와 정확히 하나의 YAML 상태 블록
- 제한 Safe YAML, alias·merge·중복 키 거부
- structural/executable 2단계 검증
- `PLAN_READY`부터 `PLAN_APPROVED`까지 allowlisted 이벤트
- document SHA-256/version CAS, 잠금, 이력, `fsync`, 원자 교체
- 제한 상대 경로와 command digest
- attempt별 evidence path/SHA-256/byte-size 검증
- TEST `tested_state_id`, QA input state, finding/risk ledger
- Worker lease 보고 시점 재검사와 Worker→aggregate QA provenance
- Phase path contract digest가 결합된 integration journal
- 최종 planning/execution/finding evidence graph 재검증
- 파생 체크박스와 상태 일관성

## 변경 절차

1. `references/plan-schema-v2.md`를 수정한다.
2. `scripts/plan_core.py`와 관련 CLI를 수정한다.
3. 양성·음성 fixture를 추가한다.
4. 전체 pytest와 `quick_validate.py`를 실행한다.
5. 패키지 manifest를 다시 생성하고 전문가 재검증 결과를 갱신한다.
