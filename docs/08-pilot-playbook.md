# 2-lane 파일럿 절차

실제 적용 전 작은 저장소에서 다음 흐름을 한 번 검증한다.

## 대상 조건

- 서로 다른 책임과 write 경로를 가진 작업 두 개
- 각 lane의 독립 테스트
- 공유 계약이 없거나 COMMON에서 먼저 확정 가능
- 시작 시 clean Git baseline

## 절차

1. candidate JSON을 작성하고 `assess_parallelism.py` 결과와 근거를 검토한다.
2. JSON·Markdown 계획을 생성하고 validator를 통과시킨다.
3. preflight에서 initial/lane baseline을 확정한다.
4. 같은 lane baseline에서 별도 Git worktree 두 개를 만든다.
5. 각 worktree에서 허용 경로만 수정·commit하고 scope checker와 독립 테스트를 실행한다.
6. ledger에 두 lane의 Git·scope·test·QA 증거를 기록한다.
7. main 통합 worktree에서 두 commit을 순차 merge한다.
8. 통합 직전 commit을 integration scope baseline으로 기록하고 전체 테스트를 실행한다.
9. ledger `status --verify-git`가 `EXECUTION_COMPLETE`인지 확인한다.

## 자동 파일럿

`tests/test_parallel_workflow_e2e.py`가 임시 Git 저장소와 실제 worktree 두 개를 만들어 위 핵심 흐름을 자동 검증한다.

- API와 Web lane이 같은 baseline에서 시작
- lane별 실제 Git scope 검사
- lane commit의 순차 merge
- 코드 수정 없는 integration의 `SCOPE_EMPTY` 허용
- 전체 unit 증거 기록 후 `EXECUTION_COMPLETE`

## 중단 기준

- 의미적 결합이 발견됨
- write 경로가 겹침
- 사용자 변경을 안전하게 보존할 수 없음
- COMMON 계약이 확정되지 않음
- 독립 테스트 또는 최종 회귀 테스트가 없음
- 통합에서 광범위한 lane 재수정이 필요함

파일럿에서 조율 비용이 절약 시간보다 크면 병렬 Workstream을 늘리지 않고 V1 직렬 계획으로 전환한다.
