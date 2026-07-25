# 프로젝트 개요

`/Volumes/Eprojects/project_202607/dev-plan-v2`는 `codex-dev-plan-orchestrator`의 원본
저장소다. 이 스킬은 v1의 강점인 **범위 고정, Phase 진행 규약, 자체 테스트, QA,
재개 가능성**을 유지한다.

## 제공 범위

- 필수 Markdown 개발 계획 생성과 형식/READY 검사
- PLAN / EXECUTE / RESUME / QA / STATUS 운영 지침
- 실제 런타임 모델 기반 Lead·Worker·QA 라우팅
- 최소 런타임 패키징

제거한 것은 상태 엔진, evidence manifest, 다중 lock, rollback manager 같은 workflow
platform 기능이다. 계획의 범위·진행·모델·QA 규약은 제거 대상이 아니다.
