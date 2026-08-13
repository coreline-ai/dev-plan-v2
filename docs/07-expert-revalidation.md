# 전문가 재검증 기준

## 유지한 원칙

- 목적·범위·제외·Phase·자체 테스트·QA 관점
- write 경로 단독 소유권과 Worker별 실제 diff 검사
- COMMON 선행, Workstream Wave, 마지막 통합 검증
- 불명확한 근거를 성공으로 추정하지 않는 fail-closed 처리

## 실개발형으로 변경한 설계

- 기본값을 병렬이 아닌 직렬로 변경
- 경로뿐 아니라 공유 계약과 semantic blocker를 판정 근거에 포함
- 고정 모델 라우팅 대신 capability와 위험도 기반 운영
- Markdown 표 대신 JSON 정본 사용
- untracked·rename·delete가 포함된 Git 직접 검사
- integration 코드 수정은 선택, 최종 전체 테스트는 필수
- DB 대신 작은 execution ledger로 재개 근거 유지

자동 merge·push, daemon, 상태 DB, 공급자 전용 모델 API는 계속 범위 밖이다.
