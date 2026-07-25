# 아키텍처

| 계층 | 책임 |
|---|---|
| `SKILL.md` | 모드, v1-plus 계획 규약, 모델 라우팅, 실행/QA 정책 |
| `new_dev_plan.py` | 풍부한 Phase 계획 템플릿 생성 |
| `validate_dev_plan.py` | 구조 검사와 `READY` 완결성 검사 |
| `references/` | 계획 형식과 실행 흐름 정본 |

계획 자체는 Markdown이지만, 목적·범위·제외 범위·Phase 상태·각 Phase의 목표/파일/태스크/
테스트/이슈/완료 조건·QA 관점을 반드시 가진다. 상태 엔진 없이도 Lead가 실제 diff와
테스트를 근거로 체크를 갱신할 수 있게 하는 구조다.
