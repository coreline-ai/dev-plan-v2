---
name: codex-dev-plan-orchestrator
description: Create phased development plans with essential scope, progress, test, QA, and fail-closed native-model routing; use for PLAN, EXECUTE, RESUME, QA, or STATUS work.
---

# Codex Dev Plan

이 스킬은 v1의 **범위 고정·Phase 진행·자체 테스트·독립 QA·재개 가능성**을 유지하는
가벼운 개발 계획 스킬이다. 계획은 다른 Lead가 이어서 실행할 수 있는 작업 계약이다.
상태 엔진, evidence DB, lock protocol, 별도 Codex CLI/API는 만들지 않는다.

## 1. 모드와 부작용

| 사용자 의도 | 모드 | 코드 수정 | 위임 |
|---|---|---:|---:|
| 개발 계획 작성·수정 | `PLAN` | 금지 | 금지 |
| 계획대로 구현 | `EXECUTE` | 허용 | 필요 시 |
| 중단 지점부터 재개 | `RESUME` | 허용 | 필요 시 |
| 독립 검토 | `QA` | 금지 | QA만 |
| 진행 상태 요약 | `STATUS` | 금지 | 금지 |

명시적인 `EXECUTE` 또는 `RESUME` 요청이 없으면 코드·테스트·계획 체크를 수정하거나
Worker를 만들지 않는다. 목적·범위·리팩터링 방향이 달라지면 기존 계획을 확장하지 말고
새 `implement_*.md`를 만든다.

## 2. PLAN: 필수 계획 규약

계획은 `<project>/dev-plan/implement_YYYYMMDD_HHMMSS.md`에 만든다. 순서는 다음과 같다.

1. `개발 목적`, `개발 범위`, `제외 범위`, `참조 문서`, `공통 진행 규칙`
2. `실행 상태 및 모델 라우팅`, `Phase 상태 요약`, `QA 관점`
3. 순서가 있는 Phase: `목표`, `Worker 배정`, `구현 태스크`, `자체 테스트`,
   `이슈 및 수정`, `완료 조건`
4. `실행 기록`

각 구현·테스트·완료 조건에는 체크박스를 사용한다. Phase 자체 테스트가 끝나기 전 다음
Phase로 넘어가지 않는다. 이슈는 발견한 Phase 안에서 기록·수정한다.

```text
python3.11 <SKILL_DIR>/scripts/new_dev_plan.py \
  --root <project> --purpose "목적" \
  --scope "src/example.py" --exclude "UI 변경" \
  --phase "핵심 구현" --test "python3.11 -m pytest tests/example"
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py <plan.md>
```

`--ready`는 실행 전 모델 preflight와 배정이 완결됐는지 검사한다. `--complete`는 실제
host 모델, 테스트, QA PASS까지 기록됐는지 검사한다.

## 3. 비협상 모델 라우팅

`EXECUTE`/`RESUME`에서 아래 조건은 권고가 아니라 게이트다.

| 역할 | 필수 배정 |
|---|---|
| Lead | 현재 Lead가 실제 지원되는 **Sol**이거나, 새 **Sol Lead**를 생성한다. 둘 다 불가하면 `BLOCKED`. |
| ROUTINE Worker | 실제 지원되는 **Terra**에만 배정한다. |
| COMPLEX Worker | 실제 지원되는 **Luna**에만 배정한다. Luna가 없으면 `BLOCKED` 또는 Terra-safe 단위로 재분해한다. |
| QA | Worker와 분리된 새 컨텍스트의 실제 지원 **Sol**에만 배정한다. |

Terra를 Luna의 조용한 대체 모델로 사용하지 않는다. 기본 세션 모델 상속, 모델명 추정,
`actual model` 누락도 성공적인 배정이 아니다.

## 4. EXECUTE와 RESUME

1. 계획 상태·현재 Phase·체크·Git diff·마지막 테스트 결과를 확인한다.
2. **실행 전에** 네이티브 위임 런타임이 제공하는 모델 목록을 조회하고, 정확한 ID를
   `확인된 런타임 모델`에 기록한다. Sol이 없으면 새 Sol Lead를 생성하거나 `BLOCKED`다.
3. Lead/각 Worker/QA에 `requested model`을 그 정확한 ID로 지정하고
   `fork_turns: "none"`(또는 동일한 최소 컨텍스트 설정)으로 생성한다.
4. 생성 후 host가 반환한 실제 모델 ID를 `actual model`에 그대로 기록한다. 반환값이
   없거나 요청 ID와 다르면 결과를 수용하지 말고 `BLOCKED`로 기록한다.
5. `--ready`를 통과한 뒤, Worker에게 한 책임 단위의 목표·허용 파일·읽을 파일·완료
   기준·테스트·짧은 보고 형식만 전달한다. Worker는 계획을 수정하지 않는다.
6. Lead가 Worker diff와 테스트를 직접 확인한 뒤 체크를 갱신한다. `RESUME`은 첫
   미완료 Phase부터 시작하며 기록이 불명확하면 완료로 추정하지 않고 `BLOCKED`다.

`PLAN` 문서는 모델 ID를 예측하지 않는다. `UNVERIFIED`/`UNASSIGNED`/`PENDING`은
DRAFT에서만 허용된다. 추론 강도는 런타임에 별도 설정했을 때만 사실대로 기록할 수 있지만,
모델 역할을 대체하는 필수 계약은 아니다.

## 5. QA와 완료

QA에는 완료 조건, diff, 변경 파일, 실제 테스트 결과만 준다. Lead의 예상 결론이나
Worker 자기평가는 주지 않는다. 새 Sol QA는 `PASS`, `FIX`, `BLOCKED` 중 하나를 반환하며
소스·계획을 직접 수정하지 않는다.

`PASS`일 때만 Phase 완료와 QA 체크를 갱신한다. 최종 완료 전에는 다음을 실행한다.

```text
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py <plan.md> --complete
```

이 검사는 Lead/Worker/QA의 `requested model == actual model`, 모든 Phase 완료, 실제
테스트·Worker 보고, QA `PASS`를 요구한다.

## 6. 공통 규칙

- 기존 계획을 덮어쓰지 않는다. 같은 workstream만 같은 파일을 갱신한다.
- 문서에 없는 기능·리팩터링·의존성을 추가하지 않는다.
- 기존 프로젝트 API·공식 SDK·표준 라이브러리를 우선한다.
- API 직접 호출, 별도 Codex CLI, 중첩 Codex 프로세스를 사용하지 않는다.
- Git diff·실제 테스트·런타임 host가 보고한 모델 ID가 실행 결과의 정본이다.

상세 형식: [계획 형식](references/plan-format.md) ·
[실행 흐름](references/execution-workflow.md)
