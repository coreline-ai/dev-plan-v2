# Parallel Dev Plan Orchestrator

병렬화를 위해 작업을 억지로 나누지 않고, 자연스럽게 독립된 책임만 Git worktree에서 안전하게 실행하도록 돕는 Codex 스킬이다.

## 언제 사용하는가

| 상황 | 선택 |
|---|---|
| 일반 개발 요청 또는 의미적으로 결합된 작업 | V1 `dev-plan-generator` |
| 공유 계약을 먼저 확정하면 구현이 분리됨 | V2 `COMMON_FIRST` |
| 목표·write 경로·테스트가 독립된 두 작업 이상 | V2 `PARALLEL_SAFE` |
| 요구사항·Git 상태가 불명확 | `BLOCKED` |

명시적 병렬 요청에도 먼저 `ASSESS`를 수행하며, 부적합하면 V2 파일을 만들지 않는다.

판정은 `필요성 → 독립성 → 실제 속도 이점` 순서로 한 번만 수행한다. 사용자 요청 수와 Workstream 수는 비교하지 않으며, 테스트·문서·QA·병렬화 전용 리팩터링을 임의 lane으로 만들지 않는다. 이점이 불명확하거나 COMMON 이후 조율 위험이 남으면 V1 직렬 경로로 즉시 전환한다.

## 빠른 시작

1. [candidate 형식](references/parallel-plan-format.md)으로 `candidate.json`을 작성한다.
2. 병렬 적합성을 확인한다.

```bash
python3.11 scripts/assess_parallelism.py candidate.json --format json
```

`SERIAL_RECOMMENDED`이면 여기서 종료한다. `dev-plan/parallel/`, worktree, ledger는 생성하지 않는다.

3. 안전한 경우 JSON 정본과 Markdown 계획을 생성한다.

```bash
python3.11 scripts/new_parallel_dev_plan.py \
  --root /path/to/project \
  --spec candidate.json \
  --format json
```

4. 생성 결과를 검증하고 실행 전 Git 상태를 확인한다.

```bash
python3.11 scripts/validate_parallel_dev_plan.py \
  /path/to/project/dev-plan/parallel/parallel_YYYYMMDD_HHMMSS.json

python3.11 scripts/preflight_parallel_exec.py \
  --repo /path/to/project \
  --plan /path/to/project/dev-plan/parallel/parallel_YYYYMMDD_HHMMSS.json \
  --baseline HEAD
```

5. Worker별 worktree 구현 후 실제 Git 변경을 검사한다.

```bash
python3.11 scripts/check_parallel_scope.py \
  --plan /path/to/parallel_plan.json \
  --scope-unit WS-01 \
  --repo /path/to/worker-worktree \
  --baseline <lane-baseline>
```

6. 검증된 실행 사실을 ledger에 기록하고 재개 상태를 확인한다.

```bash
python3.11 scripts/execution_ledger.py init \
  --plan /path/to/parallel_plan.json \
  --repo /path/to/project \
  --baseline <initial-baseline>

python3.11 scripts/execution_ledger.py record-unit \
  /path/to/parallel_plan.execution.json \
  --scope-unit WS-01 \
  --repo /path/to/worker-worktree \
  --commit HEAD \
  --test-result '{"command":"python3.11 -m pytest tests/api","exit_code":0}' \
  --qa PASS \
  --reviewer independent
```

`record-unit`은 ledger의 baseline에서 Git 변경을 다시 수집하므로 scope 결과 문자열을 사용자가 직접 지정하지 않는다.

7. 실행 완료 후 과거 Lesson 적용 판단과 occurrence 분류를 불변 sidecar에 기록한다.

```bash
python3.11 scripts/execution_outcomes.py create \
  --plan /path/to/parallel_plan.json \
  --ledger /path/to/parallel_plan.execution.json \
  --input outcomes-input.json \
  --lesson-tool-script /path/to/dev-plan-generator/scripts/dev_lesson.py \
  --format json
```

## 실패 교훈 재사용

- V1 `dev-plan-generator`를 먼저 설치하고 `python3.11 scripts/check_dev_lesson_tool.py --format json`으로 호환성을 확인한다.
- PLAN 전 V1 `dev-plan-generator`의 공통 도구로 `docs/dev-lessons/`를 검색한다.
- 관련 과거 Lesson만 candidate `references`에 넣고, 검색 0건도 정상 처리한다.
- 실행 중 Worker는 Lesson 파일을 쓰지 않고 occurrence 사실과 scope/test 증거만 Lead에게 반환한다.
- Lead는 통합·전체 QA 후 신규 Lesson을 별도 Markdown으로 기록한다.
- 모든 분류는 인접한 `parallel_*.outcomes.json`에 보존한다. sidecar 생성 시 commit diff로 scope를 재계산하고 완전한 ledger 증거, 실제 Lesson 존재, V1 검증 결과와 Lesson SHA를 확인한다. 재검증에도 V1 script가 필요하며 도구 부재 시 `record-pending`을 남긴다.
- 이미 생성된 V2 plan JSON/Markdown과 ledger hash는 Lesson 때문에 수정하지 않는다.

상세 계약은 [V2 Dev Lesson adapter](references/dev-lesson-adapter.md)를 참고한다.

## 핵심 산출물

- `parallel_*.json`: 계획 정본
- `parallel_*.md`: 사람용 표현
- `parallel_*.execution.json`: 실행·재개 증거
- `parallel_*.outcomes.json`: post-QA 교훈 적용·발생·분류 증거

## 개발 검증

```bash
python3.11 -m pytest -q
python3.11 -m compileall -q scripts tests
python3.11 scripts/package_skill.py --output /tmp/parallel-skill-package
```

상세 실행 순서는 [병렬 실행 흐름](references/parallel-execution-workflow.md)을, 첫 적용은 [2-lane 파일럿 절차](docs/08-pilot-playbook.md)를 참고한다.
