---
name: parallel-dev-plan-orchestrator
description: Assess and operate parallel development only when the user explicitly asks for 병렬개발계획, 병렬 개발 계획, or $parallel-dev-plan-orchestrator. Default to dev-plan-generator for ordinary or semantically coupled work. Create V2 plans only for two or more naturally independent workstreams with exclusive write paths and separate tests; otherwise recommend serial work or a COMMON-first flow.
---

# Parallel Dev Plan Orchestrator

이 스킬은 병렬화를 위해 작업을 억지로 쪼개지 않는다. 먼저 자연스러운 책임 단위와 의미적 결합을 분석하고, 안전한 경우에만 별도 worktree에서 동시에 실행한다.

## 1. 선택 규칙

| 요청·판정 | 처리 |
|---|---|
| 일반 `개발계획`, 단일 작업, 결합 작업 | V1 `dev-plan-generator` |
| 명시적 `병렬개발계획` | 먼저 V2 `ASSESS` |
| `SERIAL_RECOMMENDED` | V2 파일을 만들지 않고 V1/직렬 안내 |
| `COMMON_FIRST` | 공유 계약을 직렬 확정한 뒤 제한적 병렬 실행 |
| `PARALLEL_SAFE` | V2 PLAN/EXECUTE 허용 |
| 근거·Git 상태 불명확 | `BLOCKED` |

경로가 다르다는 사실만으로 독립 작업으로 보지 않는다. 공유 API·스키마·상태 모델, 설계 선행 조건, 통합 시 lane 재수정 가능성을 함께 검토한다.

## 2. 모드

| 모드 | 코드 수정 | 역할 |
|---|---:|---|
| `ASSESS` | 금지 | 직렬·COMMON 선행·병렬 안전성 판정 |
| `PLAN` | 금지 | JSON 정본과 Markdown 계획 생성 |
| `EXECUTE` / `RESUME` | 허용 | worktree 실행, scope/test/ledger 운영 |
| `QA` | 금지 | 실제 diff와 테스트 증거 검토 |
| `STATUS` | 금지 | ledger와 Git 상태 대조 |

## 3. ASSESS와 PLAN

Lead는 후보 spec에 목적, 자연스러운 책임 단위, write 경로, read context, 독립 테스트, 공유 계약, semantic blocker, 조율 위험을 사실대로 기록한다. Python 도구는 의미를 추정하지 않고 누락·경로 충돌·의존성 모순만 검증한다.

```text
python3.11 <SKILL_DIR>/scripts/assess_parallelism.py candidate.json --format json
python3.11 <SKILL_DIR>/scripts/new_parallel_dev_plan.py \
  --root <project> --spec candidate.json --format json
python3.11 <SKILL_DIR>/scripts/validate_parallel_dev_plan.py \
  <project>/dev-plan/parallel/parallel_*.json
```

계획 산출물은 한 쌍이다.

- `parallel_*.json`: scope·dependency·test의 기계 판정 정본
- `parallel_*.md`: 같은 JSON에서 렌더링한 사람용 계획

COMMON은 공유 계약을 먼저 확정할 때만 쓴다. 통합 전체 테스트는 필수지만 통합 코드 write 경로는 없어도 된다.

## 4. EXECUTE 전 gate

```text
python3.11 <SKILL_DIR>/scripts/preflight_parallel_exec.py \
  --repo <project> --plan <plan.json> --baseline <commit>
```

- clean Git baseline과 `git worktree` 지원을 확인한다.
- 사용자 변경을 동의 없이 stash·commit·삭제하지 않는다.
- COMMON이 있으면 별도 직렬 worktree에서 완료·테스트·scope 검사를 마친 commit을 만든다.
- 모든 Worker worktree는 최초 baseline이 아니라 검증된 COMMON commit에서 시작한다.
- COMMON이 없으면 모든 Worker가 같은 최초 baseline에서 시작한다.
- Worker에는 하나의 scope unit, goal, write paths, read context, tests, risk, 완료 조건만 전달한다.

모델 이름은 계획에 고정하지 않는다. `required_capabilities`에 맞는 실제 지원 모델을 사용하고 결과는 동일한 diff·scope·test·QA gate로 판정한다. actual model 검증은 `compliance.require_actual_model=true`인 경우에만 필수다.

## 5. scope·통합·재개

각 Worker 결과는 호출자가 만든 파일 목록이 아니라 해당 worktree의 실제 Git 상태로 검사한다.

```text
python3.11 <SKILL_DIR>/scripts/check_parallel_scope.py \
  --plan <plan.json> --scope-unit WS-01 \
  --repo <worker-worktree> --baseline <lane-baseline>
```

도구는 tracked·staged·unstaged·untracked·delete·rename 이전/이후 경로를 검사한다.

- `SCOPE_OK`: 선언된 write 경로 안의 변경
- `SCOPE_EMPTY`: 변경 없음; 구현 완료로 취급하지 않음
- `SCOPE_VIOLATION`: 다른 lane·무소유·제외 경로 변경
- `SCOPE_AMBIGUOUS`: 계획 또는 Git 근거가 불명확

통합은 모든 lane의 scope와 테스트가 통과한 뒤 직렬로 수행한다. lane 결함은 `REWORK-WS-*`로 되돌려 같은 범위 검사를 다시 적용한다.

실행 사실은 Markdown 체크박스가 아니라 `parallel_*.execution.json`에 기록한다.

```text
python3.11 <SKILL_DIR>/scripts/execution_ledger.py init \
  --plan <plan.json> --repo <project> --baseline <commit>
python3.11 <SKILL_DIR>/scripts/execution_ledger.py status \
  <plan.execution.json> --verify-git
```

RESUME은 ledger의 plan hash, commit 존재, scope/test/QA 상태를 Git과 대조한다. 불일치는 완료로 추정하지 않고 `RESUME_BLOCKED`다.

## 6. 위험도 기반 QA

| 위험도 | 최소 QA |
|---|---|
| low | 자동 테스트와 Lead diff 검토 |
| medium | 별도 컨텍스트의 독립 검토 |
| high | 독립 검토와 전체 회귀 테스트 |
| critical | 사용자 또는 관련 전문가 승인 |

QA에는 목적, scope 경계, 실제 diff, scope 결과, 실제 테스트 결과만 전달한다. Worker 자기평가만으로 완료하지 않는다.

## 7. 범위 불변 규칙

- 병렬화보다 올바른 책임 경계와 직렬 의존성을 우선한다.
- write 경로는 하나의 계획상 scope unit만 소유하며 read context는 겹칠 수 있다.
- 선언되지 않은 기능·리팩터링·의존성·공개 계약 변경을 통합하지 않는다.
- 테스트 명령과 종료 코드가 모두 기록되지 않으면 완료로 추정하지 않는다.
- 자동 merge·push, 상태 DB, daemon, 공급자 전용 모델 API는 이 스킬 범위 밖이다.

입력 형식과 상세 실행 절차는 [병렬 계획 형식](references/parallel-plan-format.md)과 [병렬 실행 흐름](references/parallel-execution-workflow.md)을 따른다.
