---
name: parallel-dev-plan-orchestrator
description: Create and operate parallel development master plans only when the user explicitly asks for 병렬개발계획, 병렬 개발 계획, or $parallel-dev-plan-orchestrator. Use for parallel PLAN, EXECUTE, RESUME, QA, or STATUS with two or more independent workstreams, non-overlapping paths, and separate tests. For ordinary 개발계획 or 구현 계획, use dev-plan-generator (V1) instead.
---

# Parallel Dev Plan Orchestrator

병렬 개발에서 범위 밖 변경·lane 충돌·무단 통합을 막는 V2 master 계획 스킬이다.
일반 계획의 소유자는 V1 `dev-plan-generator`다. V2는 V1을 대체하거나 V1 파일을 수정하지 않는다.

## 1. 선택 규칙과 모드

| 요청 | 사용할 스킬 | 출력 |
|---|---|---|
| `개발계획`, `개발 계획`, `구현 계획`, 단일 작업 | V1 `dev-plan-generator` | `dev-plan/implement_*.md` |
| `병렬개발계획`, `병렬 개발 계획`, 명시적 `$parallel-dev-plan-orchestrator` | 이 V2 | `dev-plan/parallel/parallel_*.md` |
| “병렬로 해줘”처럼 모호함 | workstream·경로·의존성 확인 후 선택 | 추정 금지 |

V2 `PLAN`은 아래 세 조건이 모두 확인될 때만 만든다.

1. 독립 Workstream이 둘 이상이다.
2. 허용 경로가 서로 겹치지 않는다.
3. Workstream별 독립 테스트가 있다.

하나라도 없으면 V2 계획을 만들거나 실행하지 말고 V1 또는 직렬 작업을 안내한다.

| 모드 | 코드 수정 | native 위임 |
|---|---:|---:|
| `PLAN` | 금지 | 금지 |
| `EXECUTE` / `RESUME` | 허용 | 필수 |
| `QA` | 금지 | 새 QA만 |
| `STATUS` | 금지 | 금지 |

## 2. PLAN: master 계획 생성과 범위 고정

계획에는 V1의 `개발 목적·개발 범위·제외 범위·참조 문서·공통 진행 규칙·Phase 상태 요약·QA 관점`과 Phase별 `목표·구현 태스크·자체 테스트·이슈 및 수정·완료 조건`을 포함한다.

추가로 Workstream과 `COMMON`/`INTEGRATION` 직렬 scope unit의 목표·허용/제외 경로·선행 조건·테스트를 표로 적는다.

- `COMMON`은 있을 때만 **Wave 0**에서 직렬 실행한다.
- Workstream은 **Wave 1 이상**에서 실행한다.
- `INTEGRATION`은 마지막 Wave의 단독 직렬 unit이다.
- 모든 계획상 scope unit은 정확히 하나의 Wave에 속한다.
- `REWORK-WS-*`는 실행 중 lane 결함에만 쓰는 직렬 재작업 unit이다. 계획 Wave에는 미리 넣지 않는다.
- `--previous-plan`은 이전 V1/V2 계획 경로를 참조 문서 첫 항목에만 넣고 원본을 수정하지 않는다.

```text
python3.11 <SKILL_DIR>/scripts/new_parallel_dev_plan.py \
  --root <project> --purpose "목적" --scope "범위" \
  --workstream '<WS-01 JSON>' --workstream '<WS-02 JSON>' \
  --common '<COMMON JSON>' --integration '<INTEGRATION JSON>' \
  --phase "병렬 구현" --phase "통합 검증"
python3.11 <SKILL_DIR>/scripts/validate_parallel_dev_plan.py \
  <project>/dev-plan/parallel/parallel_*.md
```

입력 JSON과 master 문서 형식은 [병렬 계획 형식](references/parallel-plan-format.md)을 따른다.

`PLAN`에 모델 ID, host actual ID, QA 결과, 실행 성공을 쓰거나 추정하지 않는다. 실행 기록은 EXECUTE 시작 시 Lead만 선택 섹션으로 추가한다.

## 3. EXECUTE / RESUME: scope gate와 모델 역할

실행 전에 clean Git baseline과 worktree 생성 가능 여부를 확인한다. 사용자 변경을 안전하게 보존할 수 없거나 공유 checkout뿐이면 `BLOCKED`이며 V1/직렬로 전환한다.

1. `COMMON`이 있으면 별도 직렬 worktree에서 먼저 완료·테스트·scope 검사를 한다.
2. 각 Worker에는 같은 baseline에서 만든 **별도 Git worktree**, 하나의 scope unit, 허용/제외 경로, 테스트, 완료 조건만 준다. master 계획은 Lead만 갱신한다.
3. Worker별 `git diff --name-only <baseline>`만 `check_parallel_scope.py`에 넣는다. 합산 diff 검사는 금지한다.
4. scope 검사와 실제 테스트를 통과한 Worker 결과만 통합한다. `INTEGRATION`은 모든 Wave 뒤에 선언된 통합 경로에서만 실행한다.
5. 통합 중 lane 코드 결함은 광범위하게 고치지 말고 해당 `REWORK-WS-*`를 직렬로 열어 같은 scope 검사를 한다.

native delegation에서는 역할별 exact override가 비협상 조건이다.

| 역할 | 필수 조건 |
|---|---|
| Lead | 실제 지원되는 Sol. 현재 Lead가 아니면 새 Sol Lead, 둘 다 불가하면 `BLOCKED` |
| ROUTINE Worker | 실제 지원되는 Terra |
| COMPLEX Worker | 실제 지원되는 Luna. Luna가 없으면 `BLOCKED` 또는 Terra-safe 단위로 재분해 |
| QA | Worker와 분리된 새 Sol 컨텍스트 |

모든 위임은 `fork_turns: "none"` 수준의 최소 컨텍스트와 정확한 요청 모델을 명시한다. host가 actual model ID를 반환하면 원문 그대로 기록한다. 반환하지 않거나 요청과 다르면 성공으로 추정하지 않고 `BLOCKED`다.

`RESUME`은 실행 기록이 없으면 미실행 PLAN의 첫 미완료 Phase부터 시작한다. 기록이 있으면 기록·Git diff·마지막 테스트를 대조하며, 불명확하면 완료로 추정하지 않는다.

자세한 순서와 실행 기록은 [병렬 실행 흐름](references/parallel-execution-workflow.md)을 따른다.

## 4. QA와 완료

QA는 Worker와 분리된 새 Sol 컨텍스트에 다음 사실만 전달한다.

- 목적·완료 조건·scope unit 경계
- 실제 per-unit/final diff와 scope 결과
- 실제 테스트 결과

QA는 `PASS` / `FIX` / `BLOCKED` 중 하나를 낸다. Lead의 예상 결론·Worker 자기평가는 전달하지 않는다. `PASS` 전에는 완료 체크를 갱신하지 않는다.

자동 테스트는 Markdown 구조, 경로 소유권, Wave 정합성, 패키지 상태만 검증한다. native delegation, host 모델 metadata, 실제 QA 성공은 Codex 호스트 smoke에서만 성공 또는 정직한 `BLOCKED`로 기록한다.

## 5. 범위 불변 규칙

- 선언되지 않은 파일·기능·리팩터링·의존성·공개 API/스키마 변경은 완료 처리하지 않는다.
- 경로 소유권은 하나의 scope unit에만 둔다. overlap, glob, 상위 경로는 계획 단계에서 거부한다.
- Lead와 독립 QA의 실제 diff 검토는 파일 경로 검사로 대체되지 않는다.
- 상태 DB, evidence 그래프, 다중 잠금, 별도 Worker 런타임, 직접 API/CLI 호출은 이 스킬 범위 밖이다.
