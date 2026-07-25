# 다이어트 재검증

## 결정

이 저장소는 workflow platform이 아니라 간단한 개발계획 스킬로 축소했다.

제거한 항목:

- event state machine과 CAS/history
- evidence manifest·attestation·workspace ID
- 다중 lock·rollback journal·workspace integration
- v1 upgrader와 실행 상태 CLI
- YAML/Markdown AST 런타임 의존성

남긴 항목:

- 새 Markdown 계획 생성
- 기본 형식 검사
- 명시적 EXECUTE/RESUME/QA 운영 지침
- 결정적 최소 패키징

## 검증 기준

자동 테스트는 생성·검증·패키징만 다룬다. 실제 native Worker 위임은 별도 운영 smoke로
명확히 분리한다.
