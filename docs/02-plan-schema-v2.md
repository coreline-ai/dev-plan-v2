# 필수 계획 규약

상세 형식은 [계획 형식](../references/plan-format.md)을 따른다.

필수 상단 섹션은 목적, 범위, 제외 범위, 참조, 공통 규칙, 실행 상태 및 모델 라우팅,
Phase 상태 요약, QA 관점, 실행 기록이다. 각 Phase는 목표·Worker 배정·구현 태스크·자체
테스트·이슈·완료 조건을 모두 가진다.

모델 배정에는 런타임의 실제 모델 목록, Lead/QA의 requested·actual model·context,
각 Phase의 등급·requested·actual model·context를 기록한다. `--ready`는 정확한 요청 ID가
실제 목록에 있고 ROUTINE=Terra/COMPLEX=Luna/Lead·QA=Sol인지 검사한다. `--complete`는
actual ID가 requested와 정확히 같은지까지 검사한다.
