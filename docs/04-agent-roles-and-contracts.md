# 역할·모델·보고 규약

| 역할 | 모델 / 권장 reasoning | 책임 |
|---|---|---|
| Lead | 실제 Sol / high | 범위·diff·테스트 확인, 체크 갱신 |
| ROUTINE Worker | 실제 Terra / medium | 한 책임 단위 구현·자체 테스트 |
| COMPLEX Worker | 실제 Luna / high | 복잡 작업. 미제공이면 BLOCKED/재분해 |
| Independent QA | 새 실제 Sol / high | diff·테스트 독립 검토 |

Worker와 QA는 `fork_turns: "none"` 수준의 최소 컨텍스트로 생성한다. 보고에는 변경 파일,
테스트, requested/actual model, reasoning effort, 위험을 남긴다. 계약은 별도 JSON 스키마가
아니라 이 필드를 담은 짧은 위임 메시지다.
