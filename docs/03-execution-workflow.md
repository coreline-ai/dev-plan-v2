# 실행 흐름

V2 병렬 EXECUTE는 clean Git baseline과 Worker별 격리 worktree가 있을 때만 수행한다. `COMMON`을 먼저 직렬 처리하고, Workstream별 baseline diff를 각각 scope checker로 검사한 뒤에만 통합한다. 마지막 `INTEGRATION`은 선언된 통합 경로에서만 실행한다.

모델 역할은 실제 EXECUTE/RESUME에서만 확인한다: Lead=Sol, ROUTINE=Terra, COMPLEX=Luna, 독립 QA=새 Sol. actual ID를 host가 제공하지 않거나 요청과 다르면 성공을 추정하지 않고 `BLOCKED`다.

세부 순서는 [병렬 실행 흐름](../references/parallel-execution-workflow.md)을 따른다.
