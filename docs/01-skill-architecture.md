# 경량 아키텍처

런타임은 두 개의 표준 라이브러리 스크립트와 두 개의 Markdown reference로 구성된다.

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 모드 판별과 Lead/Worker/QA 운영 규칙 |
| `scripts/new_dev_plan.py` | 새 Markdown 계획 생성 |
| `scripts/validate_dev_plan.py` | 필수 섹션·Phase·체크리스트 검사 |
| `references/plan-format.md` | 계획 템플릿 |
| `references/execution-workflow.md` | 실행·QA·재개 흐름 |

계획 문서는 설명과 체크리스트다. Git diff, 실제 테스트 결과, 사용자 확인이 운영상의
정본이며, 복잡한 상태·증빙 모델을 별도로 만들지 않는다.
