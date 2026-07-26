# V2 master 계획 규약

V2 계획은 V1 핵심 상단 섹션(목적·범위·제외·참조·공통 규칙·Phase 상태·QA)과 Phase별 목표·태스크·자체 테스트·이슈·완료 조건을 유지한다.

추가 구조는 다음과 같다.

- Workstream 맵: 목표, 허용/제외 경로, 선행 조건, 테스트
- 직렬 scope unit: 선택 COMMON과 필수 INTEGRATION
- Wave: COMMON은 Wave 0, Workstream은 Wave 1 이상, INTEGRATION은 마지막 Wave

모든 계획상 scope unit은 정확히 한 Wave에 속한다. 실행 중 생성하는 `REWORK-WS-*`는 실행 기록에서만 다룬다. 상세 입력·표 형식은 [병렬 계획 형식](../references/parallel-plan-format.md)을 따른다.
