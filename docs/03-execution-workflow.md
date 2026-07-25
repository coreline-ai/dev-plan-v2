# 실행 워크플로 안내

최종 갱신: `2026-07-25 KST`

## 정본

PLAN/UPGRADE/VALIDATE/EXECUTE/RESUME/QA/STATUS의 런타임 순서와 실패 복구 정본은
[`references/execution-workflow.md`](../references/execution-workflow.md)다.

사용자가 실제로 호출하는 짧은 운영 규칙은 [`SKILL.md`](../SKILL.md)에 있으며,
상세 상태 전이는
[`references/plan-schema-v2.md`](../references/plan-schema-v2.md)를 따른다.

## 현재 구현 범위

| 흐름 | 구현 상태 |
|---|---|
| 새 v2 DRAFT 생성 | 구현·테스트 완료 |
| v1 보존 업그레이드 | 구현·테스트 완료 |
| structural/executable 검증 | 구현·테스트 완료 |
| candidate event 무수정 검증 | 구현·테스트 완료 |
| Lead 상태 이벤트 원자 적용 | 구현·테스트 완료 |
| CAS·잠금·state-history | 구현·테스트 완료 |
| disposable 통합·rollback·commit marker | 구현·실증 테스트 완료 |
| Phase 경로 계약·Worker→aggregate 연결 | 구현·테스트 완료 |
| Worker/QA 네이티브 위임 절차 | `SKILL.md` 운영 계약으로 구현 |
| Luna 부재 처리 | BLOCKED + replacement 계획 정책 |
| 패키지 생성·quick validation | 구현·테스트 완료 |

## 운영 원칙

- `PLAN`과 `UPGRADE`는 제품 코드와 Worker를 건드리지 않는다.
- `EXECUTE`와 `RESUME`는 executable 검증과 execution baseline 뒤에만 시작한다.
- Worker와 QA는 계획 문서를 수정하지 않는다.
- 현재 런타임의 exact 모델 ID만 사용한다.
- writable-root 강제가 없으면 `MANIFEST_GUARDED` 보호 장치를 모두 준비한다.
- source→evidence→plan 순서의 persistent `flock`과 Plan-derived allowlist를 쓴다.
- Phase마다 새 Sol QA, 마지막에 새 최종 Sol QA를 사용한다.
- FAIL은 재작업이고 BLOCKED는 원인·해제 조건이 충족될 때까지 완료가 아니다.
