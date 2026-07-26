# 역할·범위·보고 규약

| 역할 | 책임 | 경계 |
|---|---|---|
| Sol Lead | baseline·worktree·통합·scope/test 확인·계획 체크 | Worker의 구현을 추정으로 승인하지 않음 |
| Terra ROUTINE Worker | 한 routine scope unit 구현·테스트 | 자기 worktree·허용 경로 밖 수정 금지 |
| Luna COMPLEX Worker | 복잡 scope unit 구현·테스트 | Luna 미제공이면 BLOCKED/재분해 |
| 새 Sol QA | 실제 diff·테스트의 독립 검토 | 소스·master 계획 직접 수정 금지 |

모든 위임은 exact requested model과 `fork_turns: "none"` 수준의 최소 컨텍스트를 쓴다. Worker에는 목표·허용/제외 경로·테스트·완료 조건만 전달한다.
