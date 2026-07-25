---
name: codex-dev-plan-orchestrator
description: Create concise implementation plans and guide explicit execution, resume, and independent QA with native Codex delegation. Use when a user asks for a development plan, plan-based implementation, continuation, or code review.
---

# Codex Dev Plan

프로젝트별 구현 계획을 짧고 검증 가능하게 만들고, 사용자가 명시적으로 요청한 경우에만
그 계획을 따라 구현·재개·QA한다. 이 스킬은 workflow platform이나 배포 시스템이 아니다.

## 모드

| 요청 | 모드 | 코드 수정 | 위임 |
|---|---|---:|---:|
| 계획 작성·수정 | `PLAN` | 아니오 | 아니오 |
| 계획대로 구현 | `EXECUTE` | 예 | 필요할 때만 |
| 중단 작업 계속 | `RESUME` | 예 | 필요할 때만 |
| 독립 검토 | `QA` | 아니오 | QA만 |
| 현재 상태 요약 | `STATUS` | 아니오 | 아니오 |

명시적으로 `EXECUTE` 또는 `RESUME`을 요청하지 않으면 코드·테스트·계획 파일을
수정하거나 Worker를 만들지 않는다.

## PLAN

1. 프로젝트와 기존 문서를 읽고 목적, 범위, 제외 범위, 검증 방법을 정한다.
2. 계획은 `<project>/dev-plan/implement_YYYYMMDD_HHMMSS.md`에 만든다.
3. 목적·범위·제외 범위·Phase·QA 체크리스트가 있는지만 간단히 검사한다.

```text
python3.11 <SKILL_DIR>/scripts/new_dev_plan.py \
  --root <project> --purpose "목적" --scope "변경 범위" --phase "구현"
python3.11 <SKILL_DIR>/scripts/validate_dev_plan.py \
  <project>/dev-plan/implement_*.md
```

계획은 구현 순서와 확인 항목을 설명하는 Markdown이다. 상태 DB, 이벤트 파일,
evidence manifest를 만들지 않는다.

## EXECUTE와 RESUME

1. 최신 계획과 현재 작업 트리를 읽는다.
2. 완료되지 않은 Phase를 하나 선택하고, 변경 범위와 검증 방법을 먼저 확인한다.
3. 작업이 독립적이고 분리가 유익할 때만 native Codex Worker에게 작은 단위로 위임한다.
   Worker에게 목표, 허용 변경 범위, 테스트 명령, 보고 형식만 전달한다.
4. Lead가 diff와 테스트 결과를 확인한 뒤 계획 체크리스트를 갱신한다.
5. 막히면 완료로 표시하지 말고 계획의 실행 기록에 원인·다음 행동을 짧게 적는다.

Worker에게는 계획 파일을 직접 수정하게 하지 않는다. 복잡한 worktree, 모델 enum,
attestation, 별도 CLI/API 호출을 요구하지 않는다. 범위 밖 변경이나 실패한 테스트는
Lead가 검토한 뒤 되돌리거나 사용자에게 확인한다.

## QA

QA는 가능하면 새 컨텍스트의 에이전트가 수행한다. QA에는 변경 diff, 변경 파일,
실행한 테스트와 결과, 계획의 완료 기준만 제공한다.

QA 결과는 다음 중 하나로 짧게 기록한다.

- `PASS`: 완료 기준과 테스트 결과가 충분함
- `FIX`: 수정이 필요한 항목과 재현 방법
- `BLOCKED`: 확인할 수 없는 이유와 필요한 입력

QA는 소스와 계획을 직접 수정하지 않는다. `FIX`나 `BLOCKED`를 `PASS`로 바꾸어
보고하지 않는다.

## STATUS와 보고

`STATUS`에서는 각 Phase의 체크 여부, 마지막 테스트 결과, 열린 문제, 다음 한 가지
행동만 요약한다. 완료 보고에는 변경 파일, 실제 실행한 테스트, QA 결과, 남은 위험만
적는다.

## 공통 규칙

- API 직접 호출, 별도 Codex CLI, 중첩 Codex 프로세스를 사용하지 않는다.
- 새 계획은 기존 계획을 덮어쓰지 않는다.
- 계획은 프로젝트의 설명 문서이며, Git·테스트·사용자 확인이 실제 정본이다.
- 자동으로 완료를 주장하지 않는다. 실제 테스트하지 못한 항목은 미검증으로 남긴다.

상세 형식: [계획 형식](references/plan-format.md) ·
[간단한 실행 흐름](references/execution-workflow.md)
