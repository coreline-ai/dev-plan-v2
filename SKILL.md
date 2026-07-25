---
name: codex-dev-plan-orchestrator
description: Create, upgrade, validate, execute, resume, independently QA, and report the status of codex-dev-plan/v2 implementation plans. Use when a user asks for an execution-ready implement_*.md plan, wants to upgrade a dev-plan-generator v1 document, implement or resume work from a validated plan using native Codex worker delegation, run an independent Sol QA, or inspect plan status without directly calling the OpenAI API or a separate Codex CLI process.
---

# Codex Dev Plan Orchestrator

`codex-dev-plan/v2` 계획을 생성하고 검증하며, 검증된 계획에 한해 구현·재개·독립
QA를 운영한다. 계획 Markdown이 상태의 정본이며 Lead만 상태 이벤트를 적용한다.

## 1. 먼저 모드를 판별한다

| 사용자 의도 | 모드 | 제품 코드 수정 | Worker/QA 생성 |
|---|---|---:|---:|
| 계획만 작성 | `PLAN` | 금지 | 금지 |
| 구형 계획 변환 | `UPGRADE` | 금지 | 금지 |
| 계획 검사 | `VALIDATE` | 금지 | 금지 |
| 현황 요약 | `STATUS` | 금지 | 금지 |
| 계획대로 구현 | `EXECUTE` | 허용 | 필요 시 |
| 중단 지점부터 계속 | `RESUME` | 허용 | 필요 시 |
| 별도 검수 | `QA` | 원칙상 금지 | 새 QA만 |

명시적 구현·실행·재개 요청이 없으면 `PLAN`으로 처리한다. 모호한 “진행해줘”는 현재
대화에 검증된 실행 계획과 구현 의도가 함께 있을 때만 `EXECUTE` 또는 `RESUME`으로
해석한다. 범위가 바뀌면 기존 계획을 억지로 수정하지 말고 새 계획을 만든다.
PLAN/UPGRADE/VALIDATE/STATUS는 현재 실행자가 결정적 도구로 처리한다. EXECUTE,
RESUME, QA에서 현재 실행자를 Sol로 확인하지 못할 때만 새 Sol Lead를 최소
컨텍스트로 생성하며, 생성할 수 없으면 실행을 `BLOCKED`한다.

## 2. 런타임 파일을 찾는다

이 파일이 있는 스킬 폴더를 `SKILL_DIR`로 간주한다. 스크립트는 다음처럼 실행한다.

```text
python3.11 <SKILL_DIR>/scripts/check_runtime.py
python3.11 <SKILL_DIR>/scripts/new_dev_plan.py --help
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py --help
python3.11 <SKILL_DIR>/scripts/update_plan_state.py --help
```

`check_runtime.py`가 실패하면 자동 설치하지 않는다. 출력된 Python 3.11 isolated
environment 설치 명령을 사용자에게 제시하고 승인된 환경에서 의존성을 준비한 뒤
재검증한다.

상세 규칙은 필요한 시점에만 읽는다.

- 문서 형식·상태·이벤트: `references/plan-schema-v2.md`
- 모드별 실행 순서·복구: `references/execution-workflow.md`
- Worker·QA 계약·증빙: `references/agent-contracts.md`

## 3. 공통 불변식

1. 계획 경로는 `<project-root>/dev-plan/implement_YYYYMMDD_HHMMSS.md`다.
2. `SKILL.md`와 `scripts/`는 도구이며 대상 프로젝트의 계획 상태가 아니다.
3. Worker와 QA는 현재 계획 Markdown을 수정하지 않는다.
4. Lead만 `update_plan_state.py apply-event`를 호출한다.
5. 모든 변경은 문서 SHA-256과 `document_version` compare-and-swap을 통과한다.
6. 완료 체크박스는 YAML 상태에서 파생한다. 체크박스를 직접 편집하지 않는다.
7. API 직접 호출, 별도 Codex CLI, 중첩 Codex 프로세스를 사용하지 않는다.
8. 에이전트 위임은 현재 런타임의 내장 도구만 사용한다.
9. 런타임에서 실제 제공되는 정확한 모델 ID만 기록한다. 모델을 추정하지 않는다.
10. QA PASS, 증빙, Lead 승인이 모두 없으면 완료로 보고하지 않는다.

## 4. PLAN

1. 프로젝트 루트와 기존 파일을 읽어 목적·범위·제외 범위·제약을 정한다.
2. 안전하게 추론할 수 없는 구현 경로나 테스트는 사용자에게 필요한 만큼만 확인한다.
3. 구조화된 YAML/JSON spec을 작성한다. 최소 구조는 다음과 같다.

```yaml
purpose: 인증 상태 저장을 안전하게 교체한다.
scope: [src/auth/**, tests/auth/**]
excludes: [UI 재설계]
references: [README.md]
phases:
  - name: 인증 상태 구현
    goal: 기존 호환성을 유지하며 저장 계층을 교체한다.
    tasks:
      - title: 상태 저장 계층 구현
        objective: 원자적 저장과 오류 복구를 구현한다.
        allowed_paths: [src/auth/**]
        allowed_new_paths: [src/auth/**]
        read_paths: [src/auth/**, tests/auth/**]
        dependencies: []
        complexity: ROUTINE
        acceptance_criteria: [기존 공개 동작 유지, 실패 시 데이터 보존]
        tests:
          - title: 인증 단위 테스트
            kind: command
            argv: [python3.11, -m, pytest, tests/auth]
            cwd: .
            timeout_seconds: 300
            expected_exit_codes: [0]
            env_allowlist: [PATH, LANG, LC_ALL, TMPDIR]
            network_required: false
            covers_paths: [src/auth/**, tests/auth/**]
            expected: 모든 테스트가 종료 코드 0으로 끝난다.
```

4. 새 계획을 생성한다.

```text
python3.11 <SKILL_DIR>/scripts/new_dev_plan.py \
  --root <project-root> --spec <spec.yaml>
```

5. 구조 검증을 실행한다.

```text
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py \
  <plan.md> --level structural
```

6. Git revision 또는 전체 파일 manifest와 planning evidence를 캡처한다.
7. `PLAN_READY` 이벤트 파일을 만든 뒤 파일을 바꾸지 않고 목표 상태를 검증한다.

```text
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py <plan.md> \
  --level executable --target-state READY --candidate-event <event.yaml>
```

8. 검증 성공 후에만 같은 이벤트를 원자 적용한다. `PLAN` 모드에서는 여기서 끝낸다.

## 5. UPGRADE

원본을 절대 덮어쓰지 않는다.

```text
python3.11 <SKILL_DIR>/scripts/upgrade_dev_plan.py \
  <legacy-plan.md> --root <project-root>
```

새 v2 문서에는 원본 절대 경로·SHA-256·크기를 기록한다. 확정할 수 없는 필드는
`TODO`로 남기고 `DRAFT`를 유지한다. `TODO`를 실제 프로젝트 근거로 보완한 뒤
`PLAN`의 READY candidate 검증 절차를 수행한다.

## 6. VALIDATE와 STATUS

구조 검증은 모든 상태에서 가능하다.

```text
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py <plan.md> \
  --level structural --format json
```

실행 가능성 검증은 `READY`, `IN_PROGRESS`, `QA`에서 수행한다.

```text
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py <plan.md> \
  --level executable --format json
```

종료 코드 `0`은 통과, `1`은 계획 검증 실패, `2`는 사용법·입력·내부 오류다.
`STATUS`에서는 현재 Plan/Phase/DEV/TEST/QA 상태, 차단 사유, 열린 finding, 다음
실행 가능 항목만 요약하고 파일을 변경하지 않는다.

## 7. 상태 이벤트를 적용한다

항상 현재 파일의 SHA-256과 `document_version`을 새로 읽는다. 먼저 dry-run 한다.

```text
python3.11 <SKILL_DIR>/scripts/update_plan_state.py apply-event <plan.md> \
  --event-file <event.yaml> \
  --expected-document-sha256 <sha256> \
  --expected-document-version <version> \
  --dry-run
```

diff와 전체 검증 결과가 맞으면 `--dry-run`을 제거하고 같은 입력을 적용한다. 실제
적용 전 파일이 바뀌면 새 SHA/version으로 다시 검토한다. 실패 시 우회해서 Markdown을
직접 수정하지 않는다.

대표 이벤트:

- 준비: `PLAN_READY`, `EXECUTION_STARTED`
- 구현: `TASK_ASSIGNED`, `TASK_STARTED`, `TEST_STARTED`, `TEST_REPORTED`,
  `WORKER_REPORTED`
- QA: `PHASE_QA_STARTED`, `PHASE_QA_REPORTED`, `PHASE_APPROVED`,
  `PLAN_QA_STARTED`, `FINAL_QA_REPORTED`
- 복구: `WORKER_ATTEMPT_INVALIDATED`, `QA_ATTEMPT_INVALIDATED`,
  `REWORK_REQUESTED`, `ENTITY_BLOCKED`, `BLOCK_CLEARED`, `FINDING_RESOLVED`
- 종료: `RISK_ACCEPTED`, `PLAN_APPROVED`

정확한 payload와 guard는 `references/plan-schema-v2.md`를 따른다.

## 8. EXECUTE

1. structural과 executable 검증을 모두 통과시킨다.
2. 사용자 기존 변경을 보존한 execution baseline을 원자 캡처한다.
3. `EXECUTION_STARTED` candidate 검증과 이벤트 적용을 완료한다.
4. 의존성이 끝났고 경로가 충돌하지 않는 DEV만 선택한다.
5. 실제 런타임 모델 목록을 확인한다.
6. `ROUTINE`은 Terra Worker, `COMPLEX`는 제공되는 Luna Worker에 배정한다.
7. Luna가 없으면 존재한다고 가장하지 않는다. 현재 계획을 `BLOCKED`로 만들고,
   별도의 replacement 계획에서 Terra-safe 하위 작업으로 검증 가능하게 분해한다.
8. Worker는 `fork_turns: "none"`에 해당하는 최소 컨텍스트로 생성한다.
9. 모델 enum snapshot, spawn receipt hash, agent ID, requested/actual model,
   `context_mode: NONE`, canonical `workspace_root/workspace_id`를
   `codex-runtime-attestation/v1` 파일로 저장한다.
   snapshot과 receipt는 별도 evidence 파일로 저장하고 attestation에서
   path/SHA-256/bytes로 참조한다. `MANIFEST_GUARDED`의 workspace는 source와
   그 하위가 아닌 외부 disposable 경로여야 하고, workspace ID는 canonical
   absolute path의 SHA-256에서 결정적으로 계산한다.
10. Worker에게 허용 쓰기/신규/읽기 경로, 입력 상태 ID, acceptance criteria,
   검증 명령, 증빙 위치, 금지 사항을 명시한다.
11. Worker 보고 시 배정 lease가 아직 유효한지 다시 확인하고, 실제 diff·파일
    manifest·테스트 로그·모델 ID를 Lead가 검증한다.
12. Phase마다 이전 QA와 다른 agent ID의 새 Sol QA를 생성한다.
13. QA PASS 후에만 `PHASE_APPROVED`를 적용한다.
14. 모든 Phase 뒤 새 Sol로 최종 통합 QA를 수행한다.
15. 열린 finding이 없고 최종 QA PASS일 때만 `PLAN_APPROVED`한다.

## 9. RESUME

계획의 표면 상태를 그대로 믿지 않는다.

1. 현재 plan SHA/version, Git 또는 manifest, lock, 실행 중 agent, evidence를 대조한다.
2. 완료 attempt의 증빙 hash와 tested state를 다시 확인한다.
3. lease가 끝났거나 상태가 불명확한 attempt는 무효화한다.
4. 파일 변경과 증빙이 일치하지 않으면 완료로 추정하지 말고 `BLOCKED`한다.
5. 유효한 최초 미완료 DEV 또는 QA에서 `EXECUTE` 흐름을 재개한다.
6. 이미 유효하게 끝난 작업을 다시 실행하지 않는다.

## 10. Worker 격리와 무결성

per-agent writable-root 제한이 실제 제공되면 `CAPABILITY`를 사용한다. 제공되지 않으면
`MANIFEST_GUARDED`를 사용한다. 이는 악의적 Worker에 대한 강제 sandbox가 아니라
협력적 무결성 모델이다.

`MANIFEST_GUARDED`에서 반드시 준비할 것:

- source와 그 하위 밖의 canonical disposable workspace
- 전체 보호 파일 pre/post manifest
- control-plane inventory
- 단일 integration lock과 preimage CAS
- 허용 경로 밖 변경 탐지 및 attempt 무효화
- source output state와 QA input state 동일성

하나라도 준비하지 못하면 Worker를 시작하지 말고 계획을 `BLOCKED`한다. 경로 표현은
프로젝트 상대 literal 또는 끝의 `/**`만 허용한다. 절대 경로, `..`, symlink escape,
`.git/**`, `dev-plan/**`, glob 확장은 거부한다.

결정적 도구를 다음 순서로 사용한다.

```text
workspace_guard.py snapshot ...
workspace_guard.py prepare-copy ...
workspace_guard.py verify ...
workspace_guard.py integrate ... \
  --plan-file <plan.md> --plan-id <plan-id> --phase-id <phase-id> \
  --expected-plan-sha256 <sha256> --expected-document-version <version> \
  --rollback-dir <evidence-dir>/rollback
```

`integrate`는 source preimage CAS와 허용 경로 검사를 통과한 변경만 적용하고 rollback
journal을 evidence root에 보존한다. `--allowed-path`와 `--allowed-new-path`는
Plan의 해당 Phase DEV 계약 union과 정확히 같아야 하며 journal에는 canonical
allowlist digest를 기록한다. Phase QA current attempt가 VALID/PASS가 아니거나
disposable aggregate state가 QA input과 다르면 source를 수정하지 않는다.
이어지는 계획 상태 이벤트가 실패하면 즉시
`workspace_guard.py rollback --journal <journal.json>`을 실행한다. plan 갱신 성공
전에는 journal을 삭제하지 않는다. 통합 journal은 plan/Phase/digest/version에
바인딩되며 승인 성공 후 생성된 `COMMITTED.json`이 있으면 재사용하거나 rollback할
수 없다. `output-manifest`와 `rollback-dir`는 반드시 source의
`dev-plan/evidence/` 아래에 둔다.
승인 상태 변경은 source integration lock → plan evidence control-plane lock →
plan-file lock 순서로 직렬화한다. 잠금은 삭제형 stale lock이 아니라 persistent
inode에 대한 POSIX `flock`을 사용한다. 프로세스 종료 시 커널이 소유권을 해제하므로
부분 owner JSON과 stale-lock ABA로 새 소유자의 잠금을 지우지 않는다.

Phase QA input state는 각 current VALID Worker output에서 상태 그래프로 도달하거나,
병렬 aggregate라면 각 DEV가 소유한 경로의 post-state 항목이 aggregate workspace
manifest와 정확히 같아야 한다. 이 provenance 검증 없이는 QA를 시작하거나 Phase를
승인하지 않는다.

## 11. 독립 QA

QA는 새 Sol이며 Worker 대화·의도된 정답·기존 결론을 받지 않는다. 실제 계획,
계약 manifest, input state, diff, 변경 파일, 테스트 로그만 읽는다. 현재 계획과 제품
파일을 수정하지 않는다.

판정은 `PASS`, `FAIL`, `BLOCKED` 중 하나다. finding은 severity, 재현 절차, 관련
Phase/DEV/TEST, 증빙 참조를 포함한다. QA가 파일을 수정했거나 입력 state가 달라졌으면
판정을 무효화하고 새 QA를 실행한다. FAIL은 완료가 아니라 재작업이며, 최종 QA FAIL은
가장 이른 영향 Phase부터 이후 Phase를 `REWORK_PENDING`으로 되돌린다.

## 12. 증빙과 완료 보고

attempt별 INPUT/RESULT manifest를 분리한다.

```text
dev-plan/evidence/<plan-id>/
├── baseline/
├── <task-id>/attempt-0001/
├── <qa-id>/attempt-0001/
└── state-history/
```

manifest 참조는 프로젝트 상대 경로, SHA-256, byte 크기를 모두 가진다. 테스트 PASS는
Worker의 `output_state_id`를 실제로 시험한 결과여야 한다.

최종 답변에는 다음만 명확히 보고한다.

- 변경한 Phase/DEV와 핵심 파일
- 실제 실행한 테스트와 결과
- 독립 QA verdict와 열린 finding
- 현재 계획 상태와 잔여 리스크
- `BLOCKED`라면 원인과 정확한 해제 조건

성공처럼 보이게 하기 위해 증빙 누락, 모델 대체, QA 실패, 기존 사용자 변경을 숨기지
않는다.
