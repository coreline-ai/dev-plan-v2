# V3 계획 데이터 규약

실개발형 V2의 계획 정본 schema는 `parallel-dev-plan/v3`다.

- `assessment`: 결정, 근거, semantic blocker, 공유 계약, 조율 위험
- `common`: 공유 계약을 먼저 확정할 때만 존재
- `workstreams`: goal, write paths, read context, dependencies, tests, capabilities, risk
- `integration`: 최종 테스트 필수, write paths 선택
- `waves`: COMMON 0, Workstream 1 이상, INTEGRATION 마지막
- `compliance`: actual model 검증이 필요한 특수 환경 설정

write 경로만 단독 소유권을 가지며 read context는 겹칠 수 있다. 상세 입력은 [병렬 계획 형식](../references/parallel-plan-format.md)을 따른다.
