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

## Dev Lesson 확장 재검토

- 공통 정책·도구는 일반 계획 V1이 소유하고 V2는 얇은 실행 증거 adapter만 둔다.
- 문제 발생 시에는 사실-only 후보를 남기고, 해결·검증 후 재사용 가치가 있는 항목만 승격한다.
- Lesson Markdown이 정본이며 committed index와 자동 fuzzy merge는 사용하지 않는다.
- V2 Worker는 공유 Lesson을 수정하지 않고 Lead가 통합·QA 후 단독 기록한다.
- 기존 V2 plan JSON/Markdown과 ledger hash는 Lesson 때문에 수정하지 않는다.
- `docs/dev-lessons/`는 plan unit이 소유할 수 없고 post-QA Lead만 기록한다.
- plan/ledger를 바꾸지 않는 outcomes sidecar에 적용 판단과 occurrence 분류를 보존한다.
- outcomes create는 commit diff로 scope status/files/fingerprint를 재계산하고, create/validate 모두 실제 V1 Lesson 검증을 수행한다.
- 로컬 도구가 사람 identity를 인증할 수 없으므로 high/critical active Lesson은 advisory MVP에서 `LESSON_PROMOTION_BLOCKED`로 fail-closed한다.
- MVP 적용은 advisory이며 required hard gate와 occurrence 자동 append는 실제 운영 데이터가 쌓인 뒤 별도 검토한다.

## 최종 독립 판정

- V1 구현 감사: P0 0, P1 0, `GO`.
- V1 workflow forward-eval: advisory 파일럿 `GO`.
- V2 architecture 재감사: P0 0, P1 0, `GO`.
- 회귀: V1 35 tests, V2 39 tests, compileall·diff check·Skill Creator validation·14-file V2 package 통과.
- 실제 설치본: V1 capability `LESSON_TOOL_READY`, V1 record/find/validate와 V2 plan→ledger→Lesson→outcomes→validate smoke 통과, plan/ledger SHA 불변.

남은 P2는 outcomes와 ledger hash를 함께 악의적으로 바꾸는 경우를 위한 선택적 `validate --verify-git` 또는 서명 manifest다. 현재 계약은 create 시 Git scope 재계산을 권위 gate로 사용하며 이 P2는 advisory 파일럿을 차단하지 않는다.
