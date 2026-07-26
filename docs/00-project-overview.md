# 프로젝트 개요

`/Volumes/Eprojects/project_202607/dev-plan-v2`는 V1 일반 계획과 병행하는 V2 `parallel-dev-plan-orchestrator` 원본이다.

- V1 `dev-plan-generator`: `개발계획`·`구현 계획`·단일 workstream, `dev-plan/implement_*.md`
- V2: `병렬개발계획`·`병렬 개발 계획`·명시 호출, `dev-plan/parallel/parallel_*.md`

V2는 둘 이상의 독립 workstream, 비중복 경로, 독립 테스트가 있을 때만 master 계획을 만든다. 핵심은 병렬성보다 scope unit별 실제 diff 대조로 목적 밖 변경과 lane 충돌을 막는 것이다.
