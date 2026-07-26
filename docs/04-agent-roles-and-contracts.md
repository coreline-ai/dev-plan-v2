# 역할·모델·보고 규약

| 역할 | 필수 모델 | 컨텍스트 | 책임 |
|---|---|---|---|
| Lead | 실제 지원 Sol | 현재 Sol 또는 새 `fork_turns: none` Sol | 범위·diff·테스트 확인, 체크 갱신 |
| ROUTINE Worker | 실제 지원 Terra | `fork_turns: none` | 한 책임 단위 구현·자체 테스트 |
| COMPLEX Worker | 실제 지원 Luna | `fork_turns: none` | 복잡 작업. 미제공이면 BLOCKED/재분해 |
| Independent QA | Worker와 분리된 실제 지원 Sol | 새 `fork_turns: none` | diff·테스트 독립 검토 |

위임마다 정확한 `requested model`을 지정하고 host가 반환한 `actual model`을 그대로
기록한다. 실제 ID가 누락되거나 요청과 다르면 완료를 주장할 수 없다. Worker 보고에는 변경
파일, 테스트, requested/actual model, 위험을 남긴다. 계약은 별도 JSON 스키마가 아니라 이
필드를 담은 짧은 위임 메시지다.
