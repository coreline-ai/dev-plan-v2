# 실행 흐름

상세 흐름은 [references/execution-workflow.md](../references/execution-workflow.md)를
따른다.

명시적인 실행 요청이 없으면 계획만 만든다. 실행 시에는 한 Phase씩 diff와 테스트를
확인하고, QA `FIX` 또는 `BLOCKED`를 완료로 바꾸지 않는다.
