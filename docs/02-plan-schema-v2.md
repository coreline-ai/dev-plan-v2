# codex-dev-plan/v2 계획 문서 규격

최종 갱신: `2026-07-25 KST`

## 1. 설계 목표

계획 문서는 사람이 읽기 쉬우면서 스크립트가 다음을 결정적으로 수행할 수 있어야
한다.

- 구조 및 실행 가능성 검증
- Phase·태스크·테스트·QA 식별
- 의존성 및 파일 충돌 분석
- Worker 라우팅과 중단 후 재개
- 증빙 기반 상태 전이
- Independent QA와 최종 승인

문서 인코딩은 UTF-8, 줄바꿈은 LF를 기준으로 한다.

## 2. 정본과 파싱 규칙

- 계획 Markdown 파일이 상태의 단일 정본이다.
- 최상단 YAML frontmatter는 계획 수준의 기계 판독 상태다.
- 각 엔터티는 고정된 제목과 단일 YAML fenced block을 가진다.
- 설명용 본문은 허용하지만 상태 필드를 중복 기재하지 않는다.
- 체크박스는 사람이 보는 요약이며 YAML 상태에서 결정적으로 파생된다.
- 상태 갱신기는 전체 문서를 파싱한 뒤 대상 YAML과 파생 체크박스만 변경한다.
- 알 수 없는 필드와 설명 본문은 의미 수준에서 보존한다.

### 2.1 Markdown 정규 문법

- H1은 정확히 `# implement_YYYYMMDD_HHMMSS.md`이며 실제 파일명과 일치한다.
- 파일명·H1·`plan_id`·`created_at`의 날짜와 시각은 같은 생성 시점을 나타내며,
  `dev-plan/implement_*.md` 전체에서 `plan_id` 중복을 검사한다.
- 필수 H2는 §5의 순서로 정확히 한 번씩 나타난다.
- Phase H2는 `^## Phase ([1-9][0-9]*)\\. (.+)$`이며 번호가 1부터 연속한다.
- DEV/TEST/QA H4는 각각 `^#### (DEV-[0-9]{3,}) (.+)$`,
  `^#### (TEST-[0-9]{3,}) (.+)$`, `^#### (QA-[0-9]{3,}|QA-FINAL) (.+)$`이다.
- 엔터티 제목 바로 다음 비어 있지 않은 블록은 정보 문자열이 정확히 `yaml`인 fenced
  block 하나여야 한다.
- Phase 안 H3 순서는 `목표 → 구현 태스크 → 자체 테스트 → 이슈 및 수정 → 독립 QA
  → 완료 조건`이며 각 항목은 정확히 한 번 나타난다.
- DEV/TEST/QA 상태 block 바로 다음 첫 list item은 해당 엔터티의 단일 파생
  `- [ ] 완료` 체크박스다.
- `Phase 상태 요약`은 Phase ID 순서의 `- [ ] P1 <제목> 완료` 항목을 정확히 한 개씩
  포함한다.
- 같은 엔터티 안의 두 번째 상태 YAML block, 중복 제목, 순서가 뒤바뀐 필수 섹션은
  오류다.
- 파서는 정규식만으로 문서를 부분 수정하지 않고 Markdown AST와 source span을
  사용한다.

### 2.2 제한 YAML

- UTF-8 단일 YAML 문서의 map/list/string/integer/boolean/null만 허용한다.
- 중복 키, custom tag, anchor, alias, merge key, 복합 key는 거부한다.
- 계획 파일 최대 1 MiB, YAML nesting 깊이 20, 단일 scalar 64 KiB, 전체 엔터티
  1,000개, collection item 10,000개로 제한한다.
- 생성기는 canonical key order와 들여쓰기로 직렬화한다.
- 상태 갱신기는 대상 YAML source span과 그 상태에서 파생되는 고정 체크박스
  source span만 교체하며 그 밖의 본문 byte를 보존한다.

## 3. 계획 메타데이터

```yaml
---
schema: codex-dev-plan/v2
plan_id: PLAN-20260725-193455
status: DRAFT
current_phase: P1
document_version: 0
created_at: 2026-07-25T19:34:55+09:00
updated_at: 2026-07-25T19:34:55+09:00
lead_model: gpt-5.6-sol
worker_routing: automatic
isolation_mode: MANIFEST_GUARDED
qa_model: gpt-5.6-sol
max_rework: 2
qa_timeout_seconds: 1800
max_log_bytes: 10485760
manifest_ignore:
  - .git/**
planning_revision: UNSET
planning_evidence: NONE
execution_baseline: UNSET
execution_evidence: NONE
final_approval: PENDING
residual_risks: []
finding_ledger: []
blocked_from: NONE
blocked_reason: NONE
unblock_conditions: []
---
```

필수 필드:

| 필드 | 규칙 |
|---|---|
| `schema` | 정확히 `codex-dev-plan/v2` |
| `plan_id` | `PLAN-YYYYMMDD-HHMMSS`, 파일 내·프로젝트 내 고유 |
| `status` | 허용 계획 상태 |
| `current_phase` | 존재하는 `P#`, 완료 시 `NONE` |
| `document_version` | 상태 이벤트마다 1 증가하는 0 이상의 정수 |
| `created_at`, `updated_at` | 타임존 포함 ISO 8601 |
| `lead_model`, `qa_model` | 런타임 enum에서 선택한 exact requested model 또는 `UNASSIGNED` |
| `worker_routing` | 현재는 `automatic`만 허용 |
| `isolation_mode` | `CAPABILITY` 또는 `MANIFEST_GUARDED` |
| `max_rework` | 0 이상의 정수 |
| `qa_timeout_seconds` | QA attempt 1회의 전체 제한 시간, 양의 정수 |
| `max_log_bytes` | evidence 로그 파일 1개의 최대 크기 |
| `manifest_ignore` | planning 시 고정하는 제한 matcher 목록, 기본 `.git/**`만 허용 |
| `planning_revision` | 계획 확정 시점의 Git/manifest 상태 식별자 |
| `planning_evidence` | 계획 확정 시점 snapshot의 evidence 상대 경로 |
| `execution_baseline` | `READY → IN_PROGRESS` 시 원자적으로 고정한 실행 상태 식별자 |
| `execution_evidence` | 실행 baseline의 evidence 상대 경로 |
| `final_approval` | `PENDING` 또는 `APPROVED` |
| `residual_risks` | 최종 승인 전 검토하는 구조화된 위험 목록 |
| `finding_ledger` | QA finding의 OPEN/RESOLVED/ACCEPTED_RISK 정본 |
| `blocked_from` | `BLOCKED` 진입 직전 계획 상태, 그 외에는 `NONE` |
| `blocked_reason` | 차단 원인, 차단 상태가 아니면 `NONE` |
| `unblock_conditions` | 재개에 필요한 검증 가능한 조건 목록 |

## 4. 상태값

### 계획 상태

```text
DRAFT → READY → IN_PROGRESS → QA → COMPLETED
                    ↘ BLOCKED ↗
```

허용 전이:

| 현재 | 다음 | 필수 조건 |
|---|---|---|
| `DRAFT` | `READY` | executable `--target-state READY` 검증 PASS |
| `READY` | `IN_PROGRESS` | 실행 baseline 원자적 캡처, 첫 태스크 배정 가능 |
| `READY` | `BLOCKED` | 실행 전 환경·모델·기준 상태 차단 |
| `IN_PROGRESS` | `QA` | 모든 Phase 작업과 Phase QA PASS |
| `IN_PROGRESS` | `BLOCKED` | 중단 사유와 해제 조건 기록 |
| `QA` | `COMPLETED` | `QA-FINAL` PASS 및 Lead 승인 |
| `QA` | `IN_PROGRESS` | 최종 QA FAIL과 재작업 태스크 지정 |
| `QA` | `BLOCKED` | 최종 QA BLOCKED |
| `BLOCKED` | `blocked_from` | 차단 조건 해소, 해당 상태의 재진입 조건 충족 |

`BLOCKED`로 전환할 때 `blocked_from`, `blocked_reason`, `unblock_conditions`를 반드시
기록한다. 해제 시 `blocked_from`으로만 돌아가며 세 필드를 초기화한다.
`COMPLETED`는 종료 상태다. 범위 변경 또는 후속 작업은 새 계획으로 생성한다.

계획 상태별 불변식:

| 상태 | 필수 불변식 |
|---|---|
| `DRAFT` | structural PASS, 미확정 필드 허용 |
| `READY` | target READY 검증 PASS, planning revision/evidence 존재 |
| `IN_PROGRESS` | execution baseline/evidence 존재, 활성 Phase 정확히 하나 |
| `QA` | 모든 Phase `DONE`, `current_phase=NONE`, `QA-FINAL` 실행 가능 |
| `BLOCKED` | blocked 필드 완비, 자동 Worker/QA 실행 금지 |
| `COMPLETED` | `current_phase=NONE`, `QA-FINAL PASS`, `final_approval=APPROVED`, residual risks 기록 |

### Phase 상태

```text
PENDING
IN_PROGRESS
QA
REWORK_PENDING
BLOCKED
DONE
```

- `PENDING → IN_PROGRESS`: 선행 Phase 완료, 첫 태스크 실행 가능
- `IN_PROGRESS → QA`: 모든 DEV `WORKER_DONE|DONE`, 모든 TEST `PASS`
- `QA → IN_PROGRESS`: Phase QA FAIL과 재작업 이벤트
- `QA → DONE`: 해당 Phase QA `PASS`, Lead 승인
- `DONE → IN_PROGRESS`: 최종 QA FAIL로 해당 Phase 재작업 이벤트가 생성됨
- `DONE → REWORK_PENDING`: 더 앞 Phase 재작업으로 결과가 stale됨
- `REWORK_PENDING → IN_PROGRESS`: 모든 선행 Phase가 다시 `DONE`
- 활성 상태에서 `BLOCKED`: 차단 사유와 해제 조건 기록
- `BLOCKED → blocked_from`: 차단 해소 후 재진입 검증 PASS

Phase는 순차 실행한다. `current_phase`는 활성 또는 재검증 대상 중 가장 앞 Phase
하나이며,
Phase 간 병렬 실행은 v2에서 허용하지 않는다. 같은 Phase 안의 독립 DEV만 병렬
실행할 수 있다. `lead_approval`은 기본 `PENDING`이며 `QA → DONE` 이벤트에서
`APPROVED`로 함께 변경한다.

Phase 교차 불변식:

| Phase 상태 | DEV/TEST/QA/승인 조건 |
|---|---|
| `PENDING` | DEV 미실행, TEST 미실행, QA `PENDING`, 승인 `PENDING` |
| `IN_PROGRESS` | DEV 활성/재작업 또는 upstream 변경으로 TEST 재검증 필요, 승인 `PENDING` |
| `QA` | 모든 DEV `WORKER_DONE|DONE`, 모든 TEST `PASS`, QA `PENDING|RUNNING|FINISHED` |
| `REWORK_PENDING` | 앞 Phase 재작업 완료 대기, TEST/QA 결과 `STALE`, 승인 `PENDING` |
| `DONE` | 모든 DEV `DONE`, 모든 TEST `PASS`, current QA attempt `VALID/PASS`, 승인 `APPROVED` |
| `BLOCKED` | blocked 필드 완비, 자동 실행 금지 |

### 태스크 상태

```text
PENDING
ASSIGNED
IN_PROGRESS
WORKER_DONE
REWORK
BLOCKED
DONE
```

허용 전이:

| 현재 | 다음 |
|---|---|
| `PENDING` | `ASSIGNED`, `BLOCKED` |
| `ASSIGNED` | `IN_PROGRESS`, `PENDING`, `REWORK`, `BLOCKED` |
| `IN_PROGRESS` | `WORKER_DONE`, `REWORK`, `BLOCKED` |
| `WORKER_DONE` | `DONE`, `REWORK`, `BLOCKED` |
| `REWORK` | `ASSIGNED`, `BLOCKED` |
| `BLOCKED` | 기록된 `blocked_from` |
| `DONE` | `REWORK` |

`WORKER_DONE → DONE`은 지정 검증 성공, 해당 QA `PASS`, Lead 승인 후에만 허용한다.
`DONE → REWORK`는 최종 QA FAIL finding이 이 태스크와 연결되고 계획·Phase 회귀를
같은 원자 이벤트로 적용할 때만 허용한다.
태스크가 `BLOCKED`로 전환될 때도 `blocked_from`, `blocked_reason`,
`unblock_conditions`를 태스크 YAML에 기록한다.

### 테스트 상태

```text
PENDING
RUNNING
PASS
FAIL
BLOCKED
```

- `PENDING → RUNNING`: 검증 실행 시작
- `RUNNING → PASS | FAIL | BLOCKED`: 종료 코드·실제 결과·evidence 기록
- `PASS | FAIL | BLOCKED → PENDING`: 관련 재작업 이벤트가 이전 결과를 stale 처리
- `FAIL → RUNNING`: 재작업 없는 단순 환경 재실행
- `BLOCKED → RUNNING`: 차단 해소 후 재실행

### QA 상태와 판정

```text
status: PENDING | RUNNING | FINISHED
verdict: PENDING | PASS | FAIL | BLOCKED
```

- `PENDING → RUNNING`: 새 QA 에이전트와 입력 증빙 준비 완료
- `RUNNING → FINISHED`: 구조화된 QA 보고서가 저장됨
- `RUNNING → PENDING`: timeout·agent 유실·독립성 위반으로 attempt 무효화
- `FINISHED → PENDING`: 재작업으로 이전 결과가 stale되어 새 attempt 준비
- `FINISHED/PASS`: 관련 태스크 또는 전체 계획 승인 가능
- 재검증은 동일 QA 엔터티를 덮어쓰지 않고 `attempt`를 증가시키며 새 보고서를 만든다.

QA 조합 불변식:

| 상태 | 판정/attempt 조건 |
|---|---|
| `PENDING` | `verdict=PENDING`; current attempt가 없거나 최신 attempt `INVALID/STALE` |
| `RUNNING` | `verdict=PENDING`; current attempt, agent ID, deadline 존재 |
| `FINISHED` | terminal verdict와 같은 번호의 attempt evidence manifest 존재 |

TEST `RUNNING`은 시작 시각·attempt를, `PASS|FAIL|BLOCKED`는 `actual`, 종료 시각,
exit code 또는 차단 사유, evidence manifest 참조를 필수로 한다.

QA attempt는 append-only다. attempt가 끝날 때 다음 레코드를 `attempts`에 추가한다.

```yaml
- attempt: 1
  validity: VALID
  verdict: PASS
  agent_id: runtime-agent-id
  requested_model: gpt-5.6-sol
  actual_model: NOT_REPORTED
  context_mode: NONE
  input_state_id: sha256:0123456789abcdef
  evidence_manifest:
    path: dev-plan/evidence/PLAN-20260725-193455/QA-101/attempt-0001/evidence-manifest.yaml
    sha256: 0123456789abcdef
    bytes: 2048
```

모든 DEV/TEST/QA attempt의 `validity`는 `VALID`, `INVALID`, `STALE`이다.
무수정·독립성 검사 실패 attempt는
`INVALID`, 이후 코드 상태 변경으로 더 이상 현재 상태를 증명하지 못하는 attempt는
`STALE`로 보존하고 판정 게이트에 사용하지 않는다.
승인 게이트는 `current_attempt`가 가리키는 레코드 자체가 `VALID/PASS`이고
`input_state_id`가 현재 통합 상태와 일치할 때만 통과한다. 최신 attempt가
`INVALID`면 이전 PASS를 재사용하지 않는다. 모든 이전 `critical`/`major` finding은
후속 report에서 `RESOLVED`이거나 사용자 승인 `ACCEPTED_RISK`여야 한다.
QA `current_run`은 RUNNING 동안 attempt, agent ID, requested model, optional actual
model, input state ID, contract manifest, started_at, deadline을 가진다. 종료 시
`attempts`에 결과를 append하고 `current_run: NONE`으로 바꾼다.

finding은 `QA-101/A0001/F001`처럼 `(qa_id, attempt, local_id)` qualified reference를
사용하며 계획 전체에서 고유하다. QA report 수신 이벤트는 다음 ledger를 계획
frontmatter에 append/update한다.

```yaml
finding_ledger:
  - finding_ref: QA-101/A0001/F001
    severity: major
    status: OPEN
    opened_by:
      report_manifest: dev-plan/evidence/PLAN-20260725-193455/QA-101/attempt-0001/evidence-manifest.yaml
    addressed_by: []
    resolved_by: NONE
```

`RESOLVED`는 finding을 참조한 Worker contract와 후속 QA report manifest가 모두
있어야 한다. `ACCEPTED_RISK`는 다음 구조의 `residual_risks` 항목과 사용자 승인
evidence가 있어야 한다.

```yaml
- risk_id: RISK-001
  finding_ref: QA-101/A0001/F001
  decision: ACCEPTED
  reason: 사용자 승인 사유
  approved_at: 2026-07-25T20:30:00+09:00
  approval_evidence:
    path: dev-plan/evidence/PLAN-20260725-193455/approvals/RISK-001.yaml
    sha256: 0123456789abcdef
    bytes: 1024
```

## 5. 필수 상단 섹션

```md
# implement_YYYYMMDD_HHMMSS.md

작성 일시: `YYYY-MM-DD HH:MM:SS TZ`

## 개발 목적
## 개발 범위
## 제외 범위
## 참조 문서
## 공통 진행 규칙
## Phase 상태 요약
## QA 관점
```

H1은 파일명과 정확히 일치해야 한다.

## 6. Phase 형식

````md
## Phase 1. 인증 상태 모델

```yaml
phase_id: P1
status: PENDING
depends_on: []
lead_approval: PENDING
blocked_from: NONE
blocked_reason: NONE
unblock_conditions: []
```

### 목표
- 인증 상태와 세션 만료 상태를 분리한다.

### 구현 태스크

#### DEV-101 인증 상태 모델 추가

```yaml
task_id: DEV-101
status: PENDING
attempt: 0
current_run: NONE
worker_tier: UNASSIGNED
assigned_model: UNASSIGNED
complexity: ROUTINE
blocked_from: NONE
blocked_reason: NONE
unblock_conditions: []
allowed_paths:
  - src/auth/state/**
  - tests/auth/state/**
allowed_new_paths:
  - src/auth/state/**
  - tests/auth/state/**
read_paths:
  - src/auth/state/**
  - tests/auth/state/**
dependencies: []
acceptance_criteria:
  - 기존 공개 API를 변경하지 않는다.
  - 만료와 로그아웃을 구분한다.
verification_tests:
  - TEST-101
rework_count: 0
current_evidence: NONE
attempts: []
```

- [ ] 완료
- 목표: 인증 상태와 세션 만료 상태를 분리한다.

### 자체 테스트

#### TEST-101 인증 상태 단위 테스트

```yaml
test_id: TEST-101
status: PENDING
attempt: 0
current_run: NONE
blocked_from: NONE
blocked_reason: NONE
unblock_conditions: []
scope: TASK
for_tasks:
  - DEV-101
covers_paths:
  - src/auth/state/**
  - tests/auth/state/**
kind: command
argv: ["npm", "test", "--", "auth/state"]
cwd: .
timeout_seconds: 300
expected_exit_codes: [0]
env_allowlist: ["PATH", "LANG", "LC_ALL", "TMPDIR"]
network_required: false
command_sha256: 0123456789abcdef
expected: 모든 테스트 통과
actual: NOT_RUN
evidence: NONE
results: []
```

- [ ] 완료

### 이슈 및 수정
- 발견 이슈 없음

### 독립 QA

#### QA-101 Phase 1 Independent Sol QA

```yaml
qa_id: QA-101
status: PENDING
verdict: PENDING
current_attempt: 0
current_run: NONE
blocked_from: NONE
blocked_reason: NONE
unblock_conditions: []
scope:
  - DEV-101
required_tests:
  - TEST-101
attempts: []
```

- [ ] 완료

### 완료 조건
- [ ] 모든 구현 태스크 `DONE`
- [ ] 모든 자체 테스트 `PASS`
- [ ] Independent QA Sol `PASS`
- [ ] 발견 이슈 해결
- [ ] Lead Sol Phase 승인
````

Markdown 안의 예시 fence 중첩은 구현 시 일반 YAML fenced block으로 작성하며, 파서는
제목 바로 다음 첫 YAML block을 해당 엔터티의 상태 블록으로 인식한다.

### 6.1 DEV attempt 상태

Worker attempt는 append-only이며 다음 요약을 DEV `attempts`에 추가한다.

```yaml
- attempt: 1
  validity: VALID
  assigned_model: gpt-5.6-terra
  input_state_id: sha256:0123456789abcdef
  output_state_id: sha256:fedcba9876543210
  evidence_manifest:
    path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/evidence-manifest.yaml
    sha256: 0123456789abcdef
    bytes: 4096
```

`current_evidence`는 최신 attempt의 `evidence_manifest` 참조와 동일한 map이거나
미실행 상태의 `NONE`이다. DEV `current_run`은 `ASSIGNED|IN_PROGRESS` 동안 attempt,
agent ID, requested model, input state ID, contract manifest, started_at,
lease_expires_at을 가진 map이다. attempt가 완료·무효·stale 처리되면 요약을
`attempts`에 append하고 `current_run: NONE`으로 원자 변경한다.

### 6.2 TEST result 상태

TEST `current_run`은 RUNNING 동안 test ID, attempt, 관련 task/worker attempt,
`tested_state_id`, command digest, started_at, deadline을 가진다. 완료 시 다음 결과를
`results`에 append하고 `current_run: NONE`으로 바꾼다.

```yaml
- attempt: 1
  validity: VALID
  task_refs: ["DEV-101/A0001"]
  tested_state_id: sha256:fedcba9876543210
  result: PASS
  evidence_manifest:
    path: dev-plan/evidence/PLAN-20260725-193455/TEST-101/attempt-0001/evidence-manifest.yaml
    sha256: 0123456789abcdef
    bytes: 2048
```

TEST `scope`는 `TASK|PHASE|PLAN`이다. TASK 테스트는 `for_tasks`의 Worker output,
PHASE/PLAN 테스트는 해당 aggregate state에서 실행한다. `WORKER_REPORTED`는 각
TASK 테스트의 `tested_state_id`가 Worker `output_state_id`와 일치할 때만 허용한다.
새 patch의 write paths가 TEST `covers_paths`와 겹치면 기존 결과를 `STALE`로 바꾸고
TEST를 `PENDING`으로 reset한다.

## 7. 최종 통합 QA

````md
## 최종 통합 QA

#### QA-FINAL 전체 통합 검증

```yaml
qa_id: QA-FINAL
status: PENDING
verdict: PENDING
current_attempt: 0
current_run: NONE
blocked_from: NONE
blocked_reason: NONE
unblock_conditions: []
scope:
  - P1
required_tests:
  - TEST-101
attempts: []
```

- [ ] 완료
````

`QA-FINAL.scope`는 모든 Phase ID를, `required_tests`는 전체 통합 검증에 필요한 실제
TEST ID를 명시해야 한다. `ALL_*` 같은 추상 sentinel은 허용하지 않는다.

## 8. 최종 승인

```md
## 최종 승인

- [ ] 모든 Phase 완료
- [ ] 최종 통합 QA PASS
- [ ] 잔여 리스크 기록
- [ ] Lead Sol 최종 승인
```

## 9. 체크박스 파생 규칙

- DEV 체크박스: 태스크 상태가 `DONE`일 때만 `[x]`
- TEST 체크박스: 테스트 상태가 `PASS`일 때만 `[x]`
- QA 체크박스: `status=FINISHED`이고 `verdict=PASS`일 때만 `[x]`
- Phase 요약 체크박스: Phase의 모든 완료 조건 충족 시 `[x]`
- 최종 승인 체크박스: 각 조건의 실제 상태가 참일 때만 `[x]`
- Worker와 QA는 체크박스 또는 YAML 상태를 수정하지 않는다.

Lead 승인과 잔여 위험은 각각 Phase YAML의 `lead_approval`, 계획 frontmatter의
`final_approval`, `residual_risks`가 정본이다.

## 10. 실행 준비 조건

`DRAFT → READY` 전 다음을 모두 만족해야 한다.

1. 플레이스홀더와 `TODO`가 없다. target `READY`에서는
   `execution_baseline=UNSET`, `execution_evidence=NONE`을 허용하며, target
   `IN_PROGRESS` 이상에서는 두 필드가 모두 실제 값이어야 한다.
2. 모든 필수 상단 섹션이 있다.
3. Plan/Phase/DEV/TEST/QA ID가 고유하고 형식에 맞다.
4. 의존성은 존재하는 ID를 참조하고 순환하지 않는다.
5. 모든 구현 태스크에 허용 경로가 있다.
6. 모든 구현 태스크에 병렬 충돌 분석용 `read_paths`가 있다.
7. 허용 경로가 지나치게 넓은 프로젝트 루트 glob이 아니며 정규화 후 프로젝트
   루트와 symlink 경계를 벗어나지 않는다.
8. 모든 태스크에 완료 기준이 있다.
9. 모든 태스크에 명령 또는 구체적인 수동 검증 절차가 있다.
10. 모든 Phase에 Independent QA가 있다.
11. `QA-FINAL`이 정확히 하나 있다.
12. 체크박스와 YAML 상태가 일치한다.
13. `planning_revision`과 `planning_evidence`가 캡처되어 있다.

`allowed_paths`는 제한된 프로젝트 상대 POSIX matcher만 허용한다. 값은 정규화된
literal 파일 경로 또는 한 개 이상 literal 디렉터리 segment 뒤의 terminal `/**`만
가능하다. 그 외 `*`, `?`, character class, brace, trailing slash는 금지한다.
`dir/**`는 `dir` 아래 모든 dotfile과 하위 항목을 포함하되 `dir` 자체의 삭제·rename은
포함하지 않는다. 절대 경로, 빈 경로, `.`, `..`, NUL, backslash,
`dev-plan/**`, `.git/**`는 거부한다. `cwd`, 기존 파일, 신규 파일, symlink target은
모두 realpath 기준 프로젝트 내부여야 한다. 신규 파일은 `allowed_new_paths`에
별도로 선언한다.

두 matcher는 literal이 같거나 한 directory prefix가 다른 경로의 ancestor면
겹친다. 이 규칙으로 비중첩을 증명하지 못하면 직렬 실행한다. root 전체를 덮는
matcher는 허용하지 않는다.
병렬 판정은 write/write뿐 아니라 한 태스크의 `allowed_paths|allowed_new_paths`와
다른 태스크의 `read_paths` 교집합도 충돌로 처리한다.

상태별 모델 불변식:

- `PENDING`, `REWORK`: `worker_tier`와 `assigned_model`은 `UNASSIGNED`
- `ASSIGNED`, `IN_PROGRESS`, `WORKER_DONE`: 둘 다 실제 값이며 논리 tier와 런타임
  모델 매핑이 일치
- `DONE`: 마지막 유효 attempt의 모델과 evidence 참조를 보존
- `attempt`는 배정마다 증가하며 현재 evidence attempt와 일치
- Luna 가용성은 런타임 모델 enum을 저장한 routing evidence로 증명

## 11. evidence 요구 조건

| 상태/이벤트 | 필수 evidence |
|---|---|
| 계획 `READY` | planning state와 SHA-256 |
| 계획 `IN_PROGRESS` | execution baseline과 SHA-256 |
| 태스크 `ASSIGNED` | attempt별 contract와 입력 상태 ID |
| 태스크 `WORKER_DONE` | attempt evidence manifest와 manifest가 열거한 report·pre/post state·diff·test log |
| QA `FINISHED` | attempt evidence manifest와 manifest가 열거한 원 응답·report·pre/post 보호 manifest |
| 계획 `COMPLETED` | 최종 QA report, 최종 상태 manifest, 상태 이력 |

각 attempt의 `evidence-manifest.yaml`은 모든 파일의 path, SHA-256, byte 크기,
validity, input/output state ID를 열거한다. 모든 evidence 경로는 프로젝트 상대
경로이며 해당 plan evidence root 아래로 정규화되어야 한다. symlink를 따라 evidence
root 밖으로 나갈 수 없다. 계획에는 evidence manifest 자체의 path·SHA-256·byte
크기만 참조한다.

정규 manifest:

```yaml
manifest_version: codex-evidence-manifest/v1
plan_id: PLAN-20260725-193455
entity_id: DEV-101
attempt: 1
stage: RESULT
created_at: 2026-07-25T20:10:00+09:00
validity: VALID
input_state_id: sha256:0123456789abcdef
output_state_id: sha256:fedcba9876543210
input_manifest:
  path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/input-manifest.yaml
  sha256: 0123456789abcdef
  bytes: 1024
files:
  - role: worker_report
    path: dev-plan/evidence/PLAN-20260725-193455/DEV-101/attempt-0001/worker-report.yaml
    sha256: 0123456789abcdef
    bytes: 2048
```

`stage`는 `BASELINE|INPUT|RESULT`다. 시작 이벤트는 immutable `INPUT` manifest를,
종료 이벤트는 이를 참조하는 새 `RESULT` manifest를 생성한다. manifest 자신의
digest와 byte 크기는 manifest 내부에 넣지 않고 계획 또는 상위 manifest가 참조한다.
`files`는 path 기준 정렬하고 role은 중복할 수 없다. planning/execution baseline은
`entity_id=PLAN`, `attempt=0`, `stage=BASELINE`을 사용한다.

## 12. Git 및 비-Git 기준 상태

대상 프로젝트가 Git 저장소면:

- `planning_revision`에 계획 확정 시점의 커밋 SHA를 기록한다.
- planning working tree 상태를 evidence에 저장한다.
- EXECUTE 시작 시 현재 상태를 다시 검증하고 별도 `execution_baseline`을 만든다.
- 기존 미커밋 변경을 Worker 변경으로 오인하지 않도록 baseline patch를 보존한다.

대상 프로젝트가 Git 저장소가 아니면:

- 명시적 ignore 정책을 제외한 전체 보호 트리의 경로·종류·크기·SHA-256 manifest를
  생성한다.
- `planning_revision`에 manifest 식별자를 기록한다.
- QA 전후 manifest 차이로 수정 여부와 diff 범위를 확인한다.

두 방식 모두 기준 상태를 만들 수 없으면 `EXECUTE`하지 않는다.

각 Worker attempt는 `input_state_id`와 전체 보호 범위의 pre-state manifest에서
시작하고 `output_state_id`와 post-state manifest를 생성한다. 병렬 Worker는 격리된
worktree/snapshot을 사용한다. 병렬 wave는 clean Git 대상에서만 허용하고, 동일
wave patch를 공통 input state의 별도 integration worktree에 batch 적용한다.
경로·read-set이 disjoint인지 재검증하고 통합 테스트 후 하나의 aggregate patch와
output state를 만든다. 다음 wave는 이 output state에서 시작한다.

Phase QA는 최종 integration worktree를 검증한다. QA PASS 후 Lead는 source와 plan
lock을 잡고 원본 HEAD/clean 상태와 aggregate patch preimage를 확인한 뒤
`git apply --check`와 단일 aggregate 적용을 수행한다. source output state가 QA
input state와 같을 때만 `PHASE_APPROVED`를 적용한다. plan 갱신 실패 시 journal의
reverse patch로 source를 복구하고, 복구 실패 시 계획을 `BLOCKED`로 남긴다.
dirty Git과 비-Git 대상은 v2에서 병렬 Worker를 금지하고 attempt별 순차 snapshot,
path preimage CAS, rollback journal을 사용한다.

`manifest_ignore`는 planning evidence에 값과 digest를 고정하며 실행 중 변경할 수
없다. `.git/**` 외 ignore 추가는 사용자 승인과 이유가 필요하다. attempt evidence
append sink는 post-manifest 검증이 끝난 뒤에만 쓰며, 기존 contract·diff·log는 별도
control-plane hash inventory로 보호한다. `allowed_generated_paths`는 disposable
workspace 안에서만 예외이며 실제 작업공간 ignore로 승격되지 않는다.

명령 검증은 `argv` 배열, 프로젝트 기준 `cwd`, 양의 `timeout_seconds`로 기록한다.
셸 파이프·리다이렉션·명령 치환이 필요한 경우 임의 문자열로 실행하지 않고,
프로젝트에 존재하며 검토된 스크립트 파일을 `argv`로 호출한다. 수동 검증은
`kind: manual`과 재현 가능한 `steps` 목록을 사용한다.
개별 명령 timeout의 합은 `qa_timeout_seconds` 안에서 집행하며, 로그가
`max_log_bytes`를 넘으면 원본의 해시·전체 크기·앞뒤 일부만 보존하고 잘림을
명시한다.

명령은 `shell=False`로 실행하고 `PATH`, locale, 임시 디렉터리 등 명시된 최소
환경변수만 전달한다. 토큰·키·인증 환경변수는 기본 제거하며 테스트가 네트워크나
민감 자격증명을 요구하면 계약에 표시하고 사용자 승인 또는 런타임 정책을 따른다.
수동 테스트는 `kind: manual`, `steps`, `expected`, `evidence_required`를 필수로
가지며 “확인한다” 같은 비재현적 단일 문장은 거부한다.

TEST 엔터티가 검증 명령의 유일한 정본이다. `command_sha256`은 kind, argv, cwd,
timeout, exit code, env, network 필드의 canonical serialization digest다. DEV,
Worker 계약, QA 계약은 TEST ID와 digest만 참조하며 명령을 독립 재정의하지 않는다.
`sh|bash|zsh|cmd|powershell`의 `-c`/`-Command`, `python|node|ruby|perl`의 inline
code 실행은 기본 거부한다. 필요한 셸 로직은 프로젝트 안의 검토된 script 파일로
저장하고 그 파일을 argv로 호출한다.

## 13. 상태 이벤트와 원자성

상태 변경기는 임의 `set-status`를 받지 않고 다음 이벤트만 받는다. 공통 payload는
`plan_id`, `expected_document_sha256`, `expected_document_version`, event별 entity
ID와 evidence manifest 참조다.

| 이벤트 | 허용 from·핵심 guard | 원자 변경 |
|---|---|---|
| `PLAN_READY` | Plan `DRAFT`; planning evidence 유효; target READY 불변식 PASS | Plan `READY`, planning fields, version/checks |
| `EXECUTION_STARTED` | Plan `READY`; execution candidate manifest가 현재 보호 트리와 일치 | Plan `IN_PROGRESS`, execution fields, P1 `IN_PROGRESS` |
| `TASK_ASSIGNED` | DEV `PENDING|REWORK`; 의존성·모델·격리 공간·lease 유효 | DEV `ASSIGNED`, attempt+1, 모델·contract manifest |
| `TASK_STARTED` | DEV `ASSIGNED`; input state·lease 일치 | DEV `IN_PROGRESS` |
| `TEST_STARTED` | TEST `PENDING|FAIL|BLOCKED`; TEST digest와 workspace 일치 | TEST `RUNNING`, attempt·started_at |
| `TEST_REPORTED` | TEST `RUNNING`; tested state·task attempt·결과 evidence 유효 | TEST `PASS|FAIL|BLOCKED`, actual·종료 정보·result append |
| `WORKER_REPORTED` | DEV `IN_PROGRESS`; 모든 지정 TASK TEST가 Worker output state에서 PASS; patch/evidence 유효 | DEV `WORKER_DONE`, output state·attempt manifest |
| `WORKER_ATTEMPT_INVALIDATED` | DEV `ASSIGNED|IN_PROGRESS`; timeout·agent 유실·무결성 실패 | attempt `INVALID`, DEV `REWORK` 또는 불명확 시 `BLOCKED` |
| `PHASE_QA_STARTED` | Phase `IN_PROGRESS|QA`, QA `PENDING`; 모든 DEV `WORKER_DONE|DONE`, TEST `PASS`; Sol/격리 계약 유효 | Phase `QA`, QA `RUNNING`, current_attempt+1 |
| `PHASE_QA_REPORTED` | Phase `QA`, QA `RUNNING`; current attempt response·manifest 유효 | QA `FINISHED`, verdict·attempt manifest·finding ledger; BLOCKED verdict는 cascade |
| `QA_ATTEMPT_INVALIDATED` | QA `RUNNING`; timeout·agent 유실·독립성/무수정 실패 | attempt `INVALID`, QA `PENDING/PENDING` 또는 불명확 시 Plan `BLOCKED` |
| `PHASE_APPROVED` | Phase QA current attempt `VALID/PASS`, input state=current integrated phase state | DEV `WORKER_DONE→DONE`, Phase `DONE/APPROVED`; 다음 `PENDING|REWORK_PENDING` Phase를 `IN_PROGRESS/current_phase`로 시작하거나 없으면 Plan `QA/current_phase=NONE` |
| `PLAN_QA_STARTED` | Plan `IN_PROGRESS|QA`; 모든 Phase `DONE`; QA-FINAL `PENDING`; final QA 계약 유효 | Plan `QA/current_phase=NONE`, QA-FINAL `RUNNING`, current_attempt+1 |
| `FINAL_QA_REPORTED` | Plan `QA`, QA-FINAL `RUNNING`; response·manifest 유효 | QA-FINAL `FINISHED`, verdict·attempt manifest·finding ledger |
| `REWORK_REQUESTED` | current QA `VALID/FAIL`; finding과 범위 연결; 한도 미초과 | 아래 재작업 회귀 규칙 전체 |
| `RISK_ACCEPTED` | finding `OPEN`; 명시적 사용자 승인 evidence 유효 | finding `ACCEPTED_RISK`, residual risk append |
| `ENTITY_BLOCKED` | 활성 entity; 검증 가능한 원인·해제 조건 | 아래 cascade 표의 entity·Phase·Plan `BLOCKED` |
| `BLOCK_CLEARED` | blocked 조건 해소; candidate target 불변식 PASS | entity를 `blocked_from`으로 복귀, blocked fields 초기화 |
| `PLAN_APPROVED` | QA-FINAL current attempt `VALID/PASS`; 모든 finding 닫힘 | Plan `COMPLETED/final_approval=APPROVED`, 최종 체크박스 |

차단 cascade:

| 원인 entity | 원자 변경 |
|---|---|
| Plan 환경/모델 | Plan만 `BLOCKED` |
| Phase | Phase와 Plan `BLOCKED` |
| DEV | DEV, 소속 Phase, Plan `BLOCKED` |
| TEST | TEST, 소속 Phase, Plan `BLOCKED` |
| Phase QA verdict/attempt | QA, 소속 Phase, Plan `BLOCKED` |
| QA-FINAL verdict/attempt | QA-FINAL과 Plan `BLOCKED` |

각 변경 entity에 `blocked_from`, `blocked_reason`, `unblock_conditions`를 기록한다.
`BLOCK_CLEARED` payload는 같은 cascade의 entity 목록과 각 target state를 모두
포함하며, 하위 원인이 해소되지 않으면 Plan만 먼저 해제할 수 없다.
해제 시 Plan/Phase는 기록된 `blocked_from`으로 돌아간다. DEV는 이전 attempt를
보존하고 `REWORK`, TEST는 `PENDING`/`current_run=NONE`, Phase QA와 QA-FINAL은
이전 `VALID/BLOCKED` attempt를 보존하고 `PENDING/PENDING`/`current_run=NONE`으로
전환한다. 실행 중이던 entity를 `RUNNING`으로 직접 복귀시키지 않는다.

이벤트별 추가 필수 payload:

| 이벤트군 | 필수 필드 |
|---|---|
| `PLAN_READY` | `planning_revision`, planning evidence manifest ref |
| `EXECUTION_STARTED` | `execution_baseline`, execution evidence manifest ref |
| `TASK_ASSIGNED|TASK_STARTED` | `phase_id`, `task_id`, `attempt`, contract manifest ref, lease |
| `TEST_STARTED` | `phase_id`, `test_id`, `attempt`, task refs, tested state ID, command digest, INPUT manifest |
| `TEST_REPORTED` | `phase_id`, `test_id`, `attempt`, tested state ID, 결과, RESULT manifest |
| `WORKER_REPORTED|WORKER_ATTEMPT_INVALIDATED` | `task_id`, `attempt`, input/output state, evidence manifest 또는 invalidation reason |
| `PHASE_QA_STARTED` | `phase_id`, `qa_id`, `attempt`, agent/context/model/deadline, INPUT manifest |
| `PHASE_QA_REPORTED` | `phase_id`, `qa_id`, `attempt`, verdict, RESULT manifest |
| `QA_ATTEMPT_INVALIDATED` | `qa_id`, `attempt`, termination reason, pre/post manifest refs |
| `PHASE_APPROVED` | `phase_id`, aggregate patch/state manifest ref, QA input state |
| `PLAN_QA_STARTED` | `qa_id=QA-FINAL`, attempt, final input state, agent/context/model/deadline, INPUT manifest |
| `FINAL_QA_REPORTED` | `qa_id=QA-FINAL`, attempt, verdict, RESULT manifest |
| `REWORK_REQUESTED` | `qa_id`, attempt, finding IDs, 관련 Phase/DEV/TEST IDs |
| `RISK_ACCEPTED` | qualified finding ref, risk ID/reason, 사용자 승인 evidence |
| `ENTITY_BLOCKED|BLOCK_CLEARED` | entity type/ID, reason, unblock conditions, target state evidence |
| `PLAN_APPROVED` | final QA manifest ref, residual risks, user risk approvals |

필수 필드가 없거나 event entity가 현재 계획 그래프에 없으면 `EVENT_PAYLOAD_INVALID`로
실패한다.

`PLAN_READY`, `EXECUTION_STARTED`, `BLOCK_CLEARED`처럼 현재 문서에 아직 없는 값을
검증하는 이벤트는 `--candidate-event EVENT_PAYLOAD.yaml`로 candidate 문서를
메모리에서 구성한다. planning/execution manifest와 실제 보호 트리 일치는 잠금 안에서
다시 확인한다.

Phase QA FAIL의 `REWORK_REQUESTED`는 Phase `QA → IN_PROGRESS`, 관련 DEV
`WORKER_DONE → REWORK`, 관련 TEST 결과 `STALE` 및 TEST `PENDING`, 이전 Phase QA
PASS attempt `STALE`, QA summary `PENDING/PENDING`, 승인을 `PENDING`으로 원자
변경한다.

최종 QA FAIL은 finding이 가리키는 가장 이른 Phase를 `IN_PROGRESS/current_phase`로
선택한다. 그 Phase 이후 모든 `DONE` Phase는 `REWORK_PENDING`, 모든 TEST 결과와
이전 PASS QA attempt는 `STALE`, TEST/QA summary와 승인은 `PENDING`으로 reset한다.
finding이 직접 가리키는 DEV는 `DONE → REWORK`로, 그 밖의 DEV는 `DONE`을 유지한다.
Plan은 `QA → IN_PROGRESS`, QA-FINAL summary와 최종 승인은 `PENDING`으로 바꾼다.
실패를 발생시킨 QA attempt 자체는 `VALID/FAIL` 이력으로 보존하고 finding 연결을
유지한다. 앞 Phase가 재승인되면 `PHASE_APPROVED`가 다음 `REWORK_PENDING` Phase를
하나씩 `IN_PROGRESS`로 시작한다.

모든 이벤트는 파생 체크박스, `document_version + 1`, `updated_at`, 상태 이력을 같은
메모리 트랜잭션에서 계산한다. 잠금 안에서 document digest/version, evidence와 전체
불변식을 다시 검증한 뒤 문서 파일을 한 번만 교체한다. 공통 실패 코드는
`EVENT_FROM_MISMATCH`, `GUARD_FAILED`, `EVIDENCE_INVALID`, `CAS_MISMATCH`,
`EVENT_PAYLOAD_INVALID`, `LOCK_TIMEOUT`이며 실패 시 계획 파일을 변경하지 않는다.

## 14. v1 업그레이드 규칙

- 원본 v1 파일을 덮어쓰지 않는다.
- 새로운 타임스탬프의 v2 파일을 생성한다.
- 원본 경로와 SHA-256을 참조 문서에 기록한다.
- 확정할 수 없는 필드는 `TODO` 또는 `UNSET`으로 남긴다.
- 누락 필드가 있으면 상태를 `DRAFT`로 유지한다.
- 구조 검증은 자동 실행한다.
- 누락 필드가 없으면 planning revision/evidence를 캡처하고
  `PLAN_READY` payload와
  `--level executable --candidate-event EVENT.yaml --target-state READY`를 실행한다.
- 성공하면 `PLAN_READY` 이벤트로 `READY`로 전환한다.
