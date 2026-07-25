---
name: codex-dev-plan-orchestrator
description: Create phased development plans with the essential scope, progress, model-routing, testing, and QA rules; guide explicit execution, resume, and independent QA using native Codex delegation.
---

# Codex Dev Plan

이 스킬은 v1의 **범위 고정·Phase 진행·자체 테스트·QA·재개 가능성**을 유지하면서,
실행 런타임만 가볍게 운영한다. 계획은 단순 메모가 아니라 다른 Lead가 이어서 실행할 수
있는 작업 계약이다. 단, 상태 엔진·evidence DB·별도 Codex CLI/API는 만들지 않는다.

## 1. 모드와 부작용

| 사용자 의도 | 모드 | 코드 수정 | Worker/QA 생성 |
|---|---|---:|---:|
| 개발 계획 작성·수정 | `PLAN` | 금지 | 금지 |
| 계획대로 구현 | `EXECUTE` | 허용 | 필요 시 |
| 중단 지점부터 재개 | `RESUME` | 허용 | 필요 시 |
| 독립 검토 | `QA` | 금지 | QA만 |
| 진행 상태 요약 | `STATUS` | 금지 | 금지 |

명시적인 `EXECUTE` 또는 `RESUME` 요청이 없으면 코드·테스트·계획 체크를 수정하거나
Worker를 만들지 않는다. 범위·목적·리팩터링 방향이 달라지면 기존 계획을 억지로
확장하지 말고 새 `implement_*.md`를 만든다.

## 2. PLAN: 필수 계획 규약

계획은 `<project>/dev-plan/implement_YYYYMMDD_HHMMSS.md`에 만들고, 다음 순서를
유지한다.

1. `개발 목적`, `개발 범위`, `제외 범위`, `참조 문서`, `공통 진행 규칙`
2. `실행 상태 및 모델 라우팅`, `Phase 상태 요약`, `QA 관점`
3. 순서가 있는 Phase. 각 Phase에는 `목표`, `구현 태스크`, `자체 테스트`,
   `이슈 및 수정`, `완료 조건`을 둔다.
4. `실행 기록`에는 실제 모델·추론 강도·변경 파일·테스트·QA 판정만 남긴다.

각 구현·테스트·완료 조건에는 Markdown 체크박스를 사용한다. Phase 자체 테스트가
끝나기 전 다음 Phase로 넘어가지 않는다. 이슈는 발견한 Phase 안에서 기록·수정한다.

```text
python3.11 <SKILL_DIR>/scripts/new_dev_plan.py \
  --root <project> --purpose "목적" \
  --scope "src/example.py" --exclude "UI 변경" \
  --phase "핵심 구현" --test "python3.11 -m pytest tests/example"
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py <plan.md>
```

`--ready` 검증은 구현 범위·테스트·모델 배정처럼 실행 전에 확정해야 할 placeholder가
없는지 추가로 확인한다. DRAFT 계획은 구조 검증만 통과할 수 있다.

## 3. 실행 상태와 모델 라우팅

계획의 `실행 상태 및 모델 라우팅`은 Lead만 갱신한다. 허용 상태는
`DRAFT`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE`이다.

- **Lead**: 실제 런타임에서 확인된 정확한 **Sol** 모델, 권장 추론 강도 `high`.
  Sol을 확인하거나 생성할 수 없으면 실행하지 않고 `BLOCKED`로 기록한다.
- **ROUTINE Worker**: 실제 지원되는 정확한 **Terra** 모델, 권장 `medium`.
- **COMPLEX Worker**: 실제 지원되는 정확한 **Luna** 모델, 권장 `high`.
  Luna가 없으면 Terra로 조용히 대체하지 않는다. 계획을 `BLOCKED`로 기록하거나
  Terra-safe 단위로 새 계획을 만든다.
- **Independent QA**: Worker와 다른 새 컨텍스트의 실제 **Sol** 모델, 권장 `high`.

Worker와 QA는 `fork_turns: "none"`에 해당하는 최소 컨텍스트로 생성한다. 각 실행에는
requested model, host가 반환한 actual model(노출될 때), reasoning effort를 계획의
실행 기록에 남긴다. 모델·강도를 추정하거나 상속값을 성공적인 배정으로 보고하지 않는다.

## 4. EXECUTE와 RESUME

1. 계획 상태가 `READY` 또는 `IN_PROGRESS`인지, 현재 Phase·완료 체크·Git diff·마지막
   테스트 결과가 일치하는지 확인한다.
2. 실제 런타임 모델 목록을 확인하고 위 라우팅에 맞는 Lead/Worker를 명시적으로
   선택한다. 조건을 만족하지 않으면 `BLOCKED`다.
3. Worker에게 한 책임 단위의 목표, 허용 변경 파일, 읽을 파일, 완료 기준, 테스트 명령,
   보고 형식만 전달한다. Worker는 계획 파일을 수정하지 않는다.
4. Lead가 Worker diff와 테스트를 직접 확인한 뒤 구현·테스트 체크를 갱신한다.
5. `RESUME`은 첫 미완료 Phase부터 시작한다. 상태가 불명확하면 완료로 추정하지 말고
   `BLOCKED`와 필요한 확인 사항을 기록한다.

Worker 보고에는 변경 파일, 실제 실행 명령/결과, requested/actual model, reasoning
 effort, 미해결 위험을 포함한다. 범위 밖 변경이나 실패 테스트는 Lead가 검토하고
되돌리거나 사용자에게 확인한다.

## 5. QA와 완료

QA에는 계획의 완료 조건, diff, 변경 파일, 실제 테스트 결과만 준다. Lead의 예상 결론과
Worker 자기평가는 전달하지 않는다. QA는 새 Sol 컨텍스트에서 `PASS`, `FIX`, `BLOCKED`
중 하나를 반환하며 소스·계획을 직접 수정하지 않는다.

`PASS`일 때만 해당 Phase 완료와 QA 체크를 갱신한다. `FIX`와 `BLOCKED`는 완료가
아니다. 최종 보고에는 변경 파일, 실제 테스트, Lead/Worker/QA의 모델·추론 강도,
QA 결과, 열린 위험을 적는다.

## 6. 공통 규칙

- 기존 계획을 덮어쓰지 않는다. 같은 workstream만 같은 파일을 갱신한다.
- 문서에 없는 기능·리팩터링·의존성을 추가하지 않는다.
- 기존 프로젝트 API·공식 SDK·표준 라이브러리를 우선한다.
- API 직접 호출, 별도 Codex CLI, 중첩 Codex 프로세스를 사용하지 않는다.
- Git diff·실제 테스트·사용자 확인이 실행 결과의 정본이다.

상세 형식: [계획 형식](references/plan-format.md) ·
[실행 흐름](references/execution-workflow.md)
