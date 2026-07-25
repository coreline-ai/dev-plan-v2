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
- 상태 갱신기는 대상 YAML source span만 교체하며 그 밖의 본문 byte를 보존한다.

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
qa_model: gpt-5.6-sol
max_rework: 2
qa_timeout_seconds: 1800
max_log_bytes: 10485760
planning_revision: UNSET
planning_evidence: NONE
execution_baseline: UNSET
execution_evidence: NONE
final_approval: PENDING
residual_risks: []
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
| `lead_model`, `qa_model` | 실제 모델 식별자 또는 `UNASSIGNED` |
| `worker_routing` | 현재는 `automatic`만 허용 |
| `max_rework` | 0 이상의 정수 |
| `qa_timeout_seconds` | QA attempt 1회의 전체 제한 시간, 양의 정수 |
| `max_log_bytes` | evidence 로그 파일 1개의 최대 크기 |
| `planning_revision` | 계획 확정 시점의 Git/manifest 상태 식별자 |
| `planning_evidence` | 계획 확정 시점 snapshot의 evidence 상대 경로 |
| `execution_baseline` | `READY → IN_PROGRESS` 시 원자적으로 고정한 실행 상태 식별자 |
| `execution_evidence` | 실행 baseline의 evidence 상대 경로 |
| `final_approval` | `PENDING` 또는 `APPROVED` |
| `residual_risks` | 최종 승인 전 검토하는 구조화된 위험 목록 |
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
BLOCKED
DONE
```

- `PENDING → IN_PROGRESS`: 선행 Phase 완료, 첫 태스크 실행 가능
- `IN_PROGRESS → QA`: 모든 DEV `WORKER_DONE`, 모든 TEST `PASS`
- `QA → DONE`: 해당 Phase QA `PASS`, Lead 승인
- `DONE → IN_PROGRESS`: 최종 QA FAIL로 해당 Phase 재작업 이벤트가 생성됨
- 활성 상태에서 `BLOCKED`: 차단 사유와 해제 조건 기록
- `BLOCKED → blocked_from`: 차단 해소 후 재진입 검증 PASS

Phase는 순차 실행한다. `current_phase`는 `DONE`이 아닌 가장 앞 Phase 하나이며,
Phase 간 병렬 실행은 v2에서 허용하지 않는다. 같은 Phase 안의 독립 DEV만 병렬
실행할 수 있다. `lead_approval`은 기본 `PENDING`이며 `QA → DONE` 이벤트에서
`APPROVED`로 함께 변경한다.

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
| `ASSIGNED` | `IN_PROGRESS`, `PENDING`, `BLOCKED` |
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
- `FAIL → RUNNING`: 재작업 후 재실행
- `BLOCKED → RUNNING`: 차단 해소 후 재실행

### QA 상태와 판정

```text
status: PENDING | RUNNING | FINISHED
verdict: PENDING | PASS | FAIL | BLOCKED
```

- `PENDING → RUNNING`: 새 QA 에이전트와 입력 증빙 준비 완료
- `RUNNING → FINISHED`: 구조화된 QA 보고서가 저장됨
- `FINISHED/PASS`: 관련 태스크 또는 전체 계획 승인 가능
- 재검증은 동일 QA 엔터티를 덮어쓰지 않고 `attempt`를 증가시키며 새 보고서를 만든다.

QA attempt는 append-only다. attempt가 끝날 때 다음 레코드를 `attempts`에 추가한다.

```yaml
- attempt: 1
  validity: VALID
  verdict: PASS
  agent_id: runtime-agent-id
  requested_model: gpt-5.6-sol
  context_mode: NONE
  report: dev-plan/evidence/PLAN-20260725-193455/QA-101/attempt-0001/qa-report.yaml
  report_sha256: 0123456789abcdef
```

`validity`는 `VALID` 또는 `INVALID`다. 무수정·독립성 검사 실패 attempt는
`INVALID`로 보존하고 판정 게이트에 사용하지 않는다.
승인 게이트는 최신 `VALID` attempt만 사용하며, 해당 report가 `PASS`이고
unresolved `critical` 또는 `major` finding이 없어야 한다. 이전 실패 finding과
재작업 연결은 report 및 재작업 contract의 ID 참조로 보존한다.

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
dependencies: []
acceptance_criteria:
  - 기존 공개 API를 변경하지 않는다.
  - 만료와 로그아웃을 구분한다.
verification_tests:
  - TEST-101
rework_count: 0
current_evidence: NONE
```

- [ ] 완료
- 목표: 인증 상태와 세션 만료 상태를 분리한다.

### 자체 테스트

#### TEST-101 인증 상태 단위 테스트

```yaml
test_id: TEST-101
status: PENDING
kind: command
argv: ["npm", "test", "--", "auth/state"]
cwd: .
timeout_seconds: 300
expected_exit_codes: [0]
env_allowlist: ["PATH", "LANG", "LC_ALL", "TMPDIR"]
network_required: false
expected: 모든 테스트 통과
actual: NOT_RUN
evidence: NONE
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

## 7. 최종 통합 QA

````md
## 최종 통합 QA

#### QA-FINAL 전체 통합 검증

```yaml
qa_id: QA-FINAL
status: PENDING
verdict: PENDING
current_attempt: 0
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

1. 플레이스홀더와 `TODO`, `UNSET`이 없다.
2. 모든 필수 상단 섹션이 있다.
3. Plan/Phase/DEV/TEST/QA ID가 고유하고 형식에 맞다.
4. 의존성은 존재하는 ID를 참조하고 순환하지 않는다.
5. 모든 구현 태스크에 허용 경로가 있다.
6. 허용 경로가 지나치게 넓은 프로젝트 루트 glob이 아니며 정규화 후 프로젝트
   루트와 symlink 경계를 벗어나지 않는다.
7. 모든 태스크에 완료 기준이 있다.
8. 모든 태스크에 명령 또는 구체적인 수동 검증 절차가 있다.
9. 모든 Phase에 Independent QA가 있다.
10. `QA-FINAL`이 정확히 하나 있다.
11. 체크박스와 YAML 상태가 일치한다.
12. `planning_revision`과 `planning_evidence`가 캡처되어 있다.

`allowed_paths`는 프로젝트 상대 POSIX pathspec만 허용한다. 절대 경로, 빈 경로,
`.` 전체, `..`, NUL, platform separator 혼용, `dev-plan/**`, `.git/**`는 거부한다.
symlink는 실제 경로를 해석해 프로젝트 밖이면 거부한다. 신규 파일 허용 위치는
`allowed_new_paths`로 별도 선언한다. 두 pathspec의 비중첩을 정적으로 증명하지
못하면 충돌로 간주해 직렬 실행한다.

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
| 태스크 `WORKER_DONE` | report, pre/post state, diff, test log와 각 SHA-256 |
| QA `FINISHED` | 원 응답, 정규화 report, pre/post 보호 manifest와 각 SHA-256 |
| 계획 `COMPLETED` | 최종 QA report, 최종 상태 manifest, 상태 이력 |

모든 evidence 경로는 프로젝트 상대 경로이며 해당 plan evidence root 아래로
정규화되어야 한다. symlink를 따라 evidence root 밖으로 나갈 수 없고, 파일 참조에는
SHA-256과 byte 크기를 함께 기록한다.

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
worktree/snapshot을 사용한다. Lead는 현재 원본 상태와 patch의 입력 상태가 일치할
때만 통합한다. 비-Git manifest도 ignore 정책을 명시한 전체 보호 트리를 재열거하여
허용 경로 밖 변경과 신규 파일을 검출한다.

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

## 13. 상태 이벤트와 원자성

상태 변경기는 임의 `set-status`를 받지 않고 다음 이벤트만 받는다.

```text
PLAN_READY
EXECUTION_STARTED
TASK_ASSIGNED
TASK_STARTED
WORKER_REPORTED
PHASE_QA_REPORTED
PHASE_APPROVED
PLAN_QA_STARTED
FINAL_QA_REPORTED
REWORK_REQUESTED
ENTITY_BLOCKED
BLOCK_CLEARED
PLAN_APPROVED
```

각 이벤트는 `from`, `guards`, `evidence`, 함께 변경할 엔터티, 파생 체크박스를
하나의 메모리 트랜잭션에서 계산한다. 잠금 안에서
`expected_document_sha256`과 `document_version`을 확인하고, evidence 및 전체
상태 불변식을 다시 검증한 뒤 문서 파일을 한 번만 교체한다.

최종 QA FAIL의 `REWORK_REQUESTED`는 계획 `QA → IN_PROGRESS`, 관련 Phase
`DONE → IN_PROGRESS`, 관련 DEV `DONE → REWORK`, Phase/최종 승인 초기화를 같은
원자 이벤트로 적용한다.

## 14. v1 업그레이드 규칙

- 원본 v1 파일을 덮어쓰지 않는다.
- 새로운 타임스탬프의 v2 파일을 생성한다.
- 원본 경로와 SHA-256을 참조 문서에 기록한다.
- 확정할 수 없는 필드는 `TODO` 또는 `UNSET`으로 남긴다.
- 누락 필드가 있으면 상태를 `DRAFT`로 유지한다.
- 구조 검증은 자동 실행한다.
- 누락 필드가 없으면 planning revision/evidence를 캡처하고
  `--level executable --target-state READY`를 실행한다.
- 성공하면 `PLAN_READY` 이벤트로 `READY`로 전환한다.
