# 프로젝트 개요

이 저장소는 일반 개발 계획 V1과 병행하는 V2 `parallel-dev-plan-orchestrator` 원본이다.

- V1 `dev-plan-generator`: 일반·단일·결합 작업, `dev-plan/implement_*.md`
- V2: 명시적 병렬 요청을 먼저 평가하고 안전한 경우에만 `dev-plan/parallel/parallel_*.json|md` 생성

V2의 기본값은 직렬이다. 둘 이상의 자연스러운 책임 단위, 비중복 write 경로, 독립 테스트, 의미적 결합 부재가 확인될 때만 병렬화한다. 공유 계약이 있으면 COMMON에서 먼저 확정한다.

핵심은 에이전트 수가 아니라 실제 Git 변경과 테스트 증거로 lane 경계를 지키는 것이다.
