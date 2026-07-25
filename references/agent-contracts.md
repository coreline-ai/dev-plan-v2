# 에이전트 역할과 계약

최종 갱신: `2026-07-25 KST`

## 빠른 탐색

[권한](#1-권한-매트릭스) · [Lead](#2-lead-sol-계약) ·
[라우팅](#3-worker-라우팅) · [Worker 계약](#4-worker-작업-계약) ·
[Worker 보고](#6-worker-완료-보고) ·
[QA 입력](#7-independent-qa-sol-입력-계약) · [QA 출력](#8-qa-출력-계약) ·
[독립성](#9-qa-독립성-및-무수정-검증) ·
[상태 갱신](#10-lead-상태-갱신-계약)

## 1. 권한 매트릭스

| 주체 | 계획 생성 | 제품 코드 수정 | 계획 상태 수정 | 테스트 | 최종 승인 |
|---|---:|---:|---:|---:|---:|
| Lead Sol | 허용 | 원칙적 금지 | 허용 | 조정·확인 | 허용 |
| Terra Worker | 금지 | 계약 경로만 | 금지 | 지정 범위 | 금지 |
| Luna Worker | 금지 | 계약 경로만 | 금지 | 지정 범위 | 금지 |
| Independent QA Sol | 금지 | 금지 | 금지 | 읽기·검증 목적 | 판정만 |
| 사용자 | 허용 | 허용 | 허용 | 허용 | 최종 결정 |

에이전트는 런타임 내장 위임 기능으로만 생성한다. API 또는 외부 Codex CLI를 사용하지
않는다.

## 2. Lead Sol 계약

`PLAN`, `UPGRADE`, `VALIDATE`, `STATUS`는 현재 실행자가 결정적 스크립트로
처리하며 Worker/QA/대체 Lead를 생성하지 않는다. `EXECUTE`, `RESUME`, `QA`에서
런타임이 현재 실행자를 Sol로 식별하지 못하면 새 Sol Lead를 생성하고 원 세션은
사용자 요청과 결과를 중계한다. 생성은 `fork_turns: "none"`과 정확한 Sol 모델
식별자를 사용한다. 새 Sol을 만들 수 없으면 해당 실행 모드를 `BLOCKED`한다.

### 책임

- 사용자 요구사항과 프로젝트 문서 분석
- 실행 가능한 v2 계획 생성·검증
- planning/execution 상태와 기존 사용자 변경 보존
- 의존성·경로 충돌 분석
- 런타임 모델 가용성 확인과 작업 라우팅
- 최소 권한의 Worker 계약 생성
- Worker 보고와 실제 diff 대조
- 새로운 Independent QA 준비
- 상태 전이, 재작업, Phase·최종 승인

### 금지

- 원칙적으로 Worker 대신 직접 구현하지 않는다.
- QA 실패 또는 BLOCKED를 무시하고 승인하지 않는다.
- 모델·테스트·증빙을 실행된 것처럼 꾸미지 않는다.
- 계획 범위를 임의로 확장하지 않는다.
- 사용자 기존 변경을 되돌리거나 덮어쓰지 않는다.

## 3. Worker 라우팅

### Terra 권장 작업

- 단일 책임 또는 제한된 경로
- 기존 패턴 재사용
- 명확한 완료 기준과 검증 명령
- 낮거나 중간 수준의 회귀 위험
- 독립적으로 구현·검증 가능

### Luna 권장 작업

- 다중 모듈 통합
- 복잡한 상태·비동기·동시성
- 인증·권한·데이터 마이그레이션
- 원인 불명의 복잡 결함
- 높은 회귀 위험

Luna는 런타임이 실제 모델 식별자를 제공할 때만 사용한다. 현재 환경에서 확인되지
않으면 현재 계획을 `BLOCKED`로 전환한다. 더 작은 Terra-safe 단위가 가능하면 원
계획을 참조하는 replacement 계획을 새 plan ID로 만들고 검증한다. READY 이후 계획
구조를 직접 바꾸는 `TASK_SPLIT`은 지원하지 않는다. 안전한 분할이 불가능하면
`BLOCKED`다.

가용성 정본은 런타임 위임 도구가 노출하는 모델 enum이다. Worker도
`fork_turns: "none"`과 선택한 정확한 모델 식별자로 생성하고 전체 계획 대신 해당
계약과 필요한 파일 경로만 전달한다. 동시 슬롯보다 많은 Worker는 wave로 순차
대기한다.

## 4. Worker 작업 계약

계약은 evidence 디렉터리에 YAML로 저장하며, 다음 필드를 필수로 한다.

```yaml
contract_version: codex-worker-contract/v1
plan_file: dev-plan/implement_20260725_193455.md
plan_id: PLAN-20260725-193455
phase_id: P1
task_id: DEV-101
attempt: 1
worker_tier: TERRA
assigned_model: gpt-5.6-terra
routing_reason:
  - 단일 책임
  - 기존 패턴 재사용
input_state_id: sha256:1111111111111111111111111111111111111111111111111111111111111111
lease_expires_at: 2026-07-25T20:30:00+09:00
workspace_kind: disposable-worktree
workspace_id: 20fc9eb7b204c79fa55a7b87
source_root: /absolute/project/root
workspace_root: /absolute/disposable/worker-DEV-101-attempt-0001
integration_root: /absolute/disposable/integration-P1
runtime_attestation:
  path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/runtime-attestation.json
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
  bytes: 1024

objective: 인증 상태 모델을 추가한다.

allowed_paths:
  - src/auth/state/**
  - tests/auth/state/**
allowed_new_paths:
  - src/auth/state/**
  - tests/auth/state/**
read_paths:
  - src/auth/state/**
  - tests/auth/state/**

prohibited:
  - 계획 문서 수정
  - 공개 API 변경
  - DB 스키마 변경
  - 계획 밖 리팩터링
  - 사용자 기존 변경 되돌리기

dependencies: []

acceptance_criteria:
  - 만료와 로그아웃 상태를 구분한다.
  - 기존 인증 API가 유지된다.

verification_tests:
  - test_id: TEST-101
    command_sha256: 0000000000000000000000000000000000000000000000000000000000000000

addresses_findings: []

report_required:
  - changed_files
  - implementation_summary
  - test_commands
  - test_results
  - scope_deviation
  - unresolved_risks
  - output_state_id
```

`source_root`, `workspace_root`, `integration_root`는 canonical absolute path다.
`workspace_root`는 `source_root` 바깥의 disposable 위치여야 하며 계약과 spawn
메시지에 같은 값을 사용한다. source 자체나 그 하위 경로는 거부한다.
`workspace_id`는 canonical `workspace_root` 문자열의 SHA-256 앞 24자리다.
INPUT manifest의 `workspace_root`, `workspace_id`, `input_state_id`도 계약과
일치해야 한다.

런타임 attestation은 Lead가 모델 enum 확인과 실제 spawn 직후 저장한다.

```yaml
schema: codex-runtime-attestation/v1
agent_id: runtime-agent-id
role: WORKER
worker_tier: TERRA
requested_model: gpt-5.6-terra
actual_model: NOT_REPORTED
supported_models: [gpt-5.6-sol, gpt-5.6-terra]
context_mode: NONE
workspace_root: /absolute/disposable/worker-DEV-101-attempt-0001
workspace_id: 20fc9eb7b204c79fa55a7b87
model_enum_snapshot:
  path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/model-enum-snapshot.json
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
  bytes: 512
spawn_receipt:
  path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/spawn-receipt.json
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
  bytes: 1024
spawn_receipt_sha256: 0000000000000000000000000000000000000000000000000000000000000000
created_at: 2026-07-25T20:00:00+09:00
```

요청 모델이 `supported_models`에 없거나 exact override spawn이 실패하면 attestation을
만들어 성공처럼 기록하지 않는다. `actual_model: NOT_REPORTED`는 런타임이 실제
모델을 반환하지 않았지만 exact requested override의 성공 receipt가 있을 때만 쓴다.
`supported_models`는 별도 `codex-model-enum-snapshot/v1` 파일과 정확히 같아야
하며, `spawn_receipt_sha256`는 실제 `codex-spawn-receipt/v1` 참조의 digest와
같아야 한다. receipt의 agent/model/context/workspace도 attestation과 일치해야 한다.

## 5. Worker 행동 규칙

1. 계약의 `input_state_id`와 격리 작업공간 상태가 맞는지 확인한다.
2. 허용 경로 밖 수정이 필요하면 작업을 중단하고 `BLOCKED`로 보고한다.
3. 계획 문서와 다른 Worker의 evidence를 수정하지 않는다.
4. 지정 검증을 실제 실행하고 명령·종료 코드·핵심 로그를 저장한다.
5. 테스트 실패를 숨기지 않고 실패 상태 그대로 보고한다.
6. 작업 종료 시 변경 파일과 허용 경로를 대조한다.
7. 커밋은 Lead가 명시적으로 계약에 허용한 경우에만 수행한다.
8. 원본 작업공간에 직접 patch를 적용하거나 계획 상태를 변경하지 않는다.
9. lease 만료 전에 완료하지 못하면 현재 상태와 이유를 보고하고 임의 연장하지 않는다.
10. `TASK_STARTED`에는 배정 당시의 attempt, agent ID, input state,
    `lease_expires_at`을 그대로 반환한다. 하나라도 다르거나 이미 만료됐으면 시작하지
    않는다.

## 6. Worker 완료 보고

```yaml
report_version: codex-worker-report/v1
task_id: DEV-101
attempt: 1
status: WORKER_DONE
assigned_model: gpt-5.6-terra
input_state_id: sha256:1111111111111111111111111111111111111111111111111111111111111111
output_state_id: sha256:2222222222222222222222222222222222222222222222222222222222222222
lease_expires_at: 2026-07-25T20:30:00+09:00

changed_files:
  - src/auth/state/model.ts
  - tests/auth/state/model.test.ts

implementation_summary:
  - 인증 상태와 세션 만료 상태를 분리함

tests:
  - test_id: TEST-101
    command_sha256: 0000000000000000000000000000000000000000000000000000000000000000
    argv: ["npm", "test", "--", "auth/state"]
    exit_code: 0
    result: PASS
    log: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/test.log
    log_sha256: 0000000000000000000000000000000000000000000000000000000000000000

scope_deviation: NONE
unresolved_risks: []
pre_state: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/pre-state.json
post_state: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/post-state.json
diff: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/diff.patch
diff_sha256: 0000000000000000000000000000000000000000000000000000000000000000
evidence_manifest:
  path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/evidence-manifest.yaml
  sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
  bytes: 4096
```

Worker 보고는 완료 증빙이며 승인 자체가 아니다. Lead는 실제 파일과 diff를 대조한
뒤에만 `WORKER_DONE`을 인정한다.

## 7. Independent QA Sol 입력 계약

QA는 반드시 런타임 위임 도구의 `fork_turns: "none"`과 실제 지원되는 Sol 모델
식별자를 사용해 새 컨텍스트로 생성한다. 조건을 만족하는 생성이 불가능하면
fallback하지 않고 `BLOCKED`다.

```yaml
contract_version: codex-qa-contract/v1
original_request: 사용자 원본 요구사항
plan_file: dev-plan/implement_20260725_193455.md
plan_id: PLAN-20260725-193455
phase_id: P1
qa_id: QA-101
attempt: 1
agent_id: runtime-agent-id
requested_model: gpt-5.6-sol
actual_model: NOT_REPORTED
context_mode: NONE
started_at: 2026-07-25T20:00:00+09:00
deadline: 2026-07-25T20:30:00+09:00
input_state_id: sha256:2222222222222222222222222222222222222222222222222222222222222222
workspace_kind: disposable-snapshot
source_root: /absolute/project/root
workspace_root: /absolute/disposable/QA-101-attempt-0001
workspace_id: d8eb5f109093295c8c926ca4
runtime_attestation:
  path: dev-plan/evidence/PLAN-20260725-193455/QA-101/attempt-0001/runtime-attestation.json
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
  bytes: 1024
task_contracts:
  - dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/contract.yaml
diffs:
  - dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/diff.patch
required_tests:
  - test_id: TEST-101
    command_sha256: 0000000000000000000000000000000000000000000000000000000000000000
worker_test_logs:
  - dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/test.log
write_policy: SOURCE_WRITE_FORBIDDEN_WITH_DECLARED_OUTPUTS
allowed_generated_paths:
  - .pytest_cache/**
```

`SOURCE_WRITE_FORBIDDEN_WITH_DECLARED_OUTPUTS`는 소스·계획·계약 수정은 금지하고,
disposable workspace 안의 `allowed_generated_paths` 테스트 산출물만 허용한다.
해당 경로도 realpath 기준 격리 root 밖으로 나갈 수 없다.

QA 입력에서 제외한다.

- Lead의 예상 판정
- Worker의 품질 자기평가
- 이전 QA의 결론과 대화 이력
- “완료됐다” 또는 “통과해야 한다”는 유도 문구

이전 QA가 찾은 개별 결함의 재현 조건은 재작업 계약에 포함할 수 있으나, 새 QA에는
수정된 요구사항 및 실제 diff의 일부로만 제공한다.

재작업 Worker 계약은 `addresses_findings`에 이전 finding ID를 반드시 기록한다.
후속 QA는 실제 수정과 회귀 테스트를 검증한 ID를 `resolved_findings`에 기록한다.
완료 게이트는 전체 attempt를 순회해 모든 이전 OPEN `critical|major` finding이
`RESOLVED` 또는 사용자 승인 `ACCEPTED_RISK`인지 확인한다.

## 8. QA 출력 계약

통과 예시:

```yaml
report_version: codex-qa-report/v1
qa_id: QA-101
attempt: 1
verdict: PASS
input_state_id: sha256:2222222222222222222222222222222222222222222222222222222222222222
termination_reason: COMPLETED

requirements:
  - criterion: 만료와 로그아웃 상태 구분
    status: PASS
    evidence:
      - src/auth/state/model.ts
      - tests/auth/state/model.test.ts

tests_reproduced:
  - test_id: TEST-101
    command_sha256: 0000000000000000000000000000000000000000000000000000000000000000
    argv: ["npm", "test", "--", "auth/state"]
    exit_code: 0
    result: PASS

findings: []
resolved_findings: []
residual_risks: []
files_modified_by_qa: []
```

QA는 위 구조화된 내용을 최종 응답으로 반환하며 파일을 저장하지 않는다. Lead는
응답을 secret scan하고, secret이 없을 때만 `qa-response.txt`에 byte-for-byte
저장해 원 응답과 저장 파일의 SHA-256을 기록한다. 그 후 구조만 검증해
`qa-report.yaml`로 저장하며 판정과 finding 내용을 편집하지 않는다. secret이
발견되면 raw 응답을 저장하거나 redaction된 판정을 대신 사용하지 않고 attempt를
무효화해 `BLOCKED` 처리한다.

실패 예시:

```yaml
report_version: codex-qa-report/v1
qa_id: QA-101
attempt: 1
verdict: FAIL
input_state_id: sha256:2222222222222222222222222222222222222222222222222222222222222222
termination_reason: COMPLETED

findings:
  - finding_ref: QA-101/A0001/F001
    severity: major
    status: OPEN
    file: src/auth/state/model.ts
    line: 87
    description: 만료된 로그아웃 세션이 다시 활성화될 수 있음
    evidence: 동시 상태 전이 재현 테스트 실패
    required_fix: 로그아웃 우선 전이와 회귀 테스트 추가

tests_reproduced:
  - test_id: TEST-101
    command_sha256: 0000000000000000000000000000000000000000000000000000000000000000
    argv: ["npm", "test", "--", "auth/state"]
    exit_code: 1
    result: FAIL

residual_risks: []
resolved_findings: []
files_modified_by_qa: []
```

`finding_ref`는 `(qa_id, attempt, local_id)` qualified ID다. finding `severity`는
`critical|major|minor`, `status`는 `OPEN|RESOLVED|ACCEPTED_RISK`다.
`ACCEPTED_RISK`는 Lead가 자동 부여할 수 없고 사용자 승인과 계획
`residual_risks` 참조가 필요하다.

## 9. QA 독립성 및 무수정 검증

다음 중 하나라도 해당하면 해당 QA 판정은 무효다.

- Lead 결론이나 Worker 자기평가를 사실로 전달받음
- 이전 QA 대화 전체를 상속함
- 실제 diff가 아닌 Worker 요약만 검토함
- 실행 가능한 필수 테스트를 이유 없이 실행하지 않음
- QA가 코드, 계획 또는 계약을 수정함
- QA 전후 상태 비교에서 허용되지 않은 변경이 발견됨
- 재현 가능한 증빙 없이 판정함

테스트가 캐시, 커버리지, 스냅샷 등 파일을 생성할 수 있으면 허용 산출물 경로를 QA
계약에 사전 명시한다. 예상되지 않은 산출물은 수정으로 간주한다.

evidence 저장 전 환경변수 이름 패턴과 런타임이 알고 있는 secret 값으로 로그·응답을
검사한다. 로그의 일치 값은 `[REDACTED:<name>]`으로 치환하고 redaction count와 raw
content SHA-256만 기록하며 raw content는 저장하지 않는다. diff·계약·보고서 구조
필드에서 secret이 발견되면 적용 가능한 patch를 임의 편집하지 않고 저장과 상태
전이를 중단해 `BLOCKED` 처리한다.

## 10. Lead 상태 갱신 계약

Lead는 QA 판정 내용을 편집하지 않는다. 상태 변경 전 다음을 확인한다.

- 보고서 스키마와 QA ID·attempt 일치
- 필수 테스트 결과 존재
- QA 전후 무수정 검증 PASS
- diff가 Worker 허용 경로 안에 있음
- 재작업 횟수 한도 미초과

그 후 `update_plan_state.py apply-event`에 `--expected-document-sha256`과
`--dry-run`을 사용한다. 실제 적용은 새 잠금 안에서 문서와 evidence를 다시 읽고
동일한 digest·version·게이트를 확인한 뒤 수행한다.
