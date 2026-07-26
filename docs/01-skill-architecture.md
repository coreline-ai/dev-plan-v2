# 아키텍처

| 계층 | 책임 |
|---|---|
| `SKILL.md` | 모드, 필수 계획 규약, fail-closed 모델 라우팅, 실행/QA 정책 |
| `new_dev_plan.py` | Phase와 Worker 배정 표준 템플릿 생성 |
| `validate_dev_plan.py` | 구조, READY preflight, DONE의 exact actual-model 검사 |
| `references/` | 계획 필드와 실행 흐름 정본 |

계획 자체는 Markdown이며 목적·범위·제외 범위·Phase 상태·각 Phase의 목표/Worker 배정/
태스크/테스트/이슈/완료 조건·QA 관점을 가진다. 별도 상태 엔진 없이 Lead가 실제 diff,
테스트, host 모델 ID를 근거로 체크를 갱신한다.
