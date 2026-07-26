# 실행 흐름

상세 흐름은 [실행 흐름](../references/execution-workflow.md)을 따른다.

실행 전에는 런타임 모델 목록을 확인하고, 현재 Lead가 Sol이 아니면 새 Sol Lead를
`fork_turns: none`으로 만든다. ROUTINE은 정확한 Terra, COMPLEX는 정확한 Luna, QA는
Worker와 분리된 새 Sol로 명시 위임한다. Luna가 없으면 Terra로 대체하지 않고 `BLOCKED`
또는 Terra-safe 재분해다.

각 생성의 requested/host actual 모델 ID를 기록하며, actual이 없거나 다르면 결과를
수용하지 않는다. Lead는 diff·테스트를 재검증하고 QA는 독립적으로 PASS/FIX/BLOCKED를 낸다.
