# 에이전트 역할·계약 안내

최종 갱신: `2026-07-25 KST`

## 정본

Lead/Worker/Independent QA의 입력·출력·증빙 계약 정본은
[`references/agent-contracts.md`](../references/agent-contracts.md)다.

실제 스킬 동작 지시는 [`SKILL.md`](../SKILL.md)의 EXECUTE, RESUME, Worker 격리,
독립 QA 절을 따른다.

## 역할 경계

| 역할 | 허용 | 금지 |
|---|---|---|
| Lead Sol | 검증, 계약 생성, 상태 이벤트, 승인 | 미검증 완료 처리, 모델 추정 |
| Terra/Luna Worker | 허용 경로 구현, 자체 테스트, 결과 반환 | 계획·evidence 정본 수정, 범위 확장 |
| Independent QA Sol | 실제 state/diff/log 검증, verdict·finding 반환 | 코드·계획 수정, 기존 결론 상속 |

## 구현된 강제 장치

- Lead 전용 `update_plan_state.py apply-event`
- SHA-256와 `document_version` CAS
- attempt별 contract/input/result evidence
- Worker output state와 TEST tested state 연결
- Worker lease의 시작·완료 시점 검증과 Phase aggregate provenance
- 별도 model-enum snapshot·spawn receipt와 결합된 runtime attestation
- event/attestation/INPUT·RESULT workspace root·ID 일치 검증
- QA PASS 이전 Phase/Plan 승인 거부
- invalid attempt와 rework 이력 보존
- finding ledger와 사용자 승인 evidence가 있는 risk acceptance

## 런타임 제약

현재 환경에서 per-agent writable-root 강제 기능이 확인되지 않았으므로 기본 격리는
`MANIFEST_GUARDED`다. 이는 협력적 무결성 모델이며 hostile sandbox가 아니다.
disposable workspace, 전체 manifest, control-plane inventory, persistent `flock`,
preimage CAS 중 하나라도 준비되지 않으면 실행을 `BLOCKED`한다.
