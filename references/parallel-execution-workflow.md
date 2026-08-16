# 병렬 실행·재개·QA 흐름

## 1. ASSESS

1. 사용자 완료 기준과 최소 직렬 구현 경로를 짧게 확인한다.
2. Workstream 제거 테스트로 없어도 되는 테스트·문서·QA·리팩터링 lane을 제거한다.
3. 남은 작업의 공유 API·스키마·상태 모델, 선행 설계, 독립 테스트를 확인한다.
4. 동시 실행 이득이 조율·worktree·통합·재작업 비용보다 명확히 큰지 확인한다.
5. 계획 생성 전에 scope별 과거 Dev Lesson을 검색하고 관련 항목만 candidate references에 추가한다. Lesson은 새 lane을 만들지 않는다.
6. `assessment_reasons`가 없거나 COMMON 이후 residual `coordination_risks`가 남으면 `SERIAL_RECOMMENDED`다.
7. `SERIAL_RECOMMENDED`면 V2 산출물 없이 V1 경로를 한 번 반환하고 ASSESS를 반복하지 않는다.
8. `COMMON_FIRST`면 원래 필요한 공유 계약을 소유하는 COMMON unit을 먼저 선언한다.
9. `COMMON_FIRST` 또는 `PARALLEL_SAFE`일 때만 PLAN을 한 번 실행해 JSON/Markdown 한 쌍을 만든다.

사용자 요청 수와 Workstream 수는 판정 기준이 아니다. 의미가 불명확한 경우 질문 루프를 늘리지 않고 직렬로 전환하며, `BLOCKED`는 입력·Git·권한·baseline 같은 실제 실행 근거가 없을 때 사용한다.

## 2. 실행 전 gate

```text
python3.11 <SKILL_DIR>/scripts/preflight_parallel_exec.py \
  --repo <project> --plan <plan.json> --baseline <commit>
```

- Git 저장소와 baseline commit이 실제로 존재해야 한다.
- main checkout이 clean하지 않으면 사용자 변경을 자동 조작하지 않고 차단한다.
- Git worktree를 사용할 수 있어야 한다.
- COMMON이 있으면 최초 preflight는 `PREFLIGHT_READY_COMMON_ONLY`를 반환한다.

COMMON을 별도 직렬 worktree에서 구현·검사·commit한 뒤 다시 확인한다.

```text
python3.11 <SKILL_DIR>/scripts/preflight_parallel_exec.py \
  --repo <project> --plan <plan.json> --baseline <initial> \
  --common-commit <verified-common-commit>
```

반환된 `lane_baseline`으로 모든 Worker worktree를 만든다.

## 3. Wave 실행과 scope 검사

Worker에는 하나의 unit, goal, write paths, read context, tests, risk, 완료 조건만 전달한다. 모델은 `required_capabilities`와 실제 host 지원 범위에서 선택한다. 문제 발생 시 Worker는 Lesson 파일을 직접 쓰지 않고 occurrence 사실과 scope/commit/test 증거만 Lead에게 반환한다.

각 Worker 구현 후 실제 Git 변경을 검사한다.

```text
python3.11 <SKILL_DIR>/scripts/check_parallel_scope.py \
  --plan <plan.json> --scope-unit WS-01 \
  --repo <worker-worktree> --baseline <lane-baseline> --format json
```

scope checker는 `git diff -M --name-status -z`와 `git ls-files --others --exclude-standard -z`를 사용한다. rename/copy는 이전·이후 경로를 모두 검사한다.

- `SCOPE_OK`만 lane 구현 성공 후보가 된다.
- `SCOPE_EMPTY`는 구현 완료가 아니다.
- `SCOPE_VIOLATION`은 통합하지 않는다.
- `SCOPE_AMBIGUOUS`는 계획 또는 Git 근거부터 바로잡는다.

## 4. 통합과 재작업

1. 같은 Wave의 모든 lane이 scope와 테스트를 통과한 뒤 순차 통합한다.
2. integration write 경로가 없으면 코드 수정 없이 최종 테스트만 실행할 수 있다.
3. 통합 중 lane 코드 결함은 `REWORK-WS-*`로 원 lane에 돌려보낸다.
4. REWORK도 원 Workstream write 경로와 같은 scope 검사를 받는다.
5. 선언되지 않은 광범위 수정은 새 계획 또는 직렬 작업으로 분리한다.
6. 전체 QA 후 Lead가 occurrence 후보를 합쳐 `plan-only | existing-reference | new-lesson`으로 분류한다.
7. 신규 Lesson은 V1 공통 도구로 별도 `docs/dev-lessons/`에 기록하고 기존 plan JSON/Markdown을 수정하지 않는다.
8. 모든 적용 판단과 분류를 `parallel_*.outcomes.json`에 기록한다. 도구가 없으면 `record-pending`으로 보존한다.

## 5. 실행 ledger와 RESUME

```text
python3.11 <SKILL_DIR>/scripts/execution_ledger.py init \
  --plan <plan.json> --repo <project> --baseline <commit>
```

unit 결과에는 repo, commit, scope status, 모든 테스트 명령·종료 코드, QA, reviewer를 기록한다. 모델 metadata는 제공될 때만 기록하며 compliance 설정이 켜진 경우에만 필수다.

```text
python3.11 <SKILL_DIR>/scripts/execution_ledger.py status \
  <plan.execution.json> --verify-git
```

plan hash 또는 Git commit 증거가 다르면 `RESUME_BLOCKED`다. 불일치를 완료로 추정하지 않는다.

## 6. 위험도 기반 QA

- low: 자동 테스트와 Lead diff 검토
- medium: 별도 컨텍스트의 독립 검토
- high: 독립 검토와 전체 회귀 테스트
- critical: 사용자 또는 관련 전문가 승인

QA에는 목적·scope·실제 diff·scope 결과·테스트 결과만 전달한다. Worker 자기평가는 완료 증거가 아니다.

Dev Lesson의 검색·증거·Lead-only 기록 상세는 [V2 Dev Lesson adapter](dev-lesson-adapter.md)를 따른다.

```text
python3.11 <SKILL_DIR>/scripts/execution_outcomes.py create \
  --plan <plan.json> --ledger <plan.execution.json> \
  --input outcomes-input.json \
  --lesson-tool-script <DEV_PLAN_SKILL_DIR>/scripts/dev_lesson.py \
  --format json

python3.11 <SKILL_DIR>/scripts/execution_outcomes.py validate \
  <plan.outcomes.json> \
  --lesson-tool-script <DEV_PLAN_SKILL_DIR>/scripts/dev_lesson.py \
  --format json
```

`create`는 plan과 정확히 일치하는 unit 집합, scope/test/QA/reviewer/commit 증거, Git object와 현재 unit HEAD를 확인하고 commit diff에서 scope status/files/fingerprint를 다시 계산한다. sidecar에는 `verified_lessons`의 repo-relative path와 SHA가 들어가며 `validate`도 V1 capability와 모든 Lesson을 다시 검증한다. `LESSON_TOOL_UNAVAILABLE`이면 두 명령 모두 `--lesson-tool-script`를 생략하고 Lesson ID를 주장하지 않는 `record-pending`만 사용한다.
