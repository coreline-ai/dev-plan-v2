# 실행 흐름

`ASSESS → PLAN → PREFLIGHT → COMMON → WORKSTREAM → SCOPE/TEST → INTEGRATION → QA` 순서다.

COMMON이 있으면 검증된 COMMON commit을 모든 Worker의 lane baseline으로 사용한다. scope checker는 Worker worktree에서 tracked·untracked·delete·rename을 직접 수집한다. 호출자가 제공한 파일 목록은 완료 근거가 아니다.

모델은 required capabilities와 host 지원 범위에서 선택하며 일반 모드에서는 모델 metadata보다 diff·test·QA 증거를 우선한다. 세부 순서는 [병렬 실행 흐름](../references/parallel-execution-workflow.md)을 따른다.
