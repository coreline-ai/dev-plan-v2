# 프로젝트 개요

`/Volumes/Eprojects/project_202607/dev-plan-v2`는 `codex-dev-plan-orchestrator`의 원본
저장소다. 이 스킬은 v1의 **범위 고정, Phase 진행, 자체 테스트, 독립 QA, 재개 가능성**과
**역할별 실제 모델 라우팅**을 유지한다.

## 제공 범위

- Markdown 개발 계획 생성과 구조/READY/완료 검사
- PLAN / EXECUTE / RESUME / QA / STATUS 운영 지침
- Lead Sol, ROUTINE Terra, COMPLEX Luna, 새 QA Sol의 fail-closed 배정
- requested/host actual 모델 ID와 최소 컨텍스트 기록
- 최소 런타임 패키징

제거한 것은 상태 엔진, evidence manifest, 다중 lock, rollback manager 같은 workflow
platform 기능이다. 모델 역할 분리·정확한 override·Phase/검증 규약은 제거 대상이 아니다.
