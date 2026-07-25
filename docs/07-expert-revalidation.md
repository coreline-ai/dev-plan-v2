# 계획 규약 재균형 기록

## 문제

초기 경량화는 workflow platform 코드를 제거하는 데는 성공했지만, v1의 핵심인 범위,
진행, 자체 테스트, QA, 재개 규약까지 지나치게 축소했다. 또한 Lead Sol / ROUTINE Terra /
COMPLEX Luna / 새 QA Sol의 모델 라우팅을 실행 계획에서 빠뜨렸다.

## 보완

- 필수 Phase 템플릿 복원
- 상단 범위·제외·참조·공통 규칙·Phase 상태 요약·QA 관점 복원
- Phase별 목표·태스크·자체 테스트·이슈·완료 조건 복원
- `DRAFT`~`DONE`의 가벼운 상태 기록과 `--ready` 검사 추가
- 실제 requested/actual model과 reasoning effort를 실행 기록에 남기는 모델 라우팅 복원

## 유지한 경량화

- event state machine, evidence manifest, workspace ID, 다중 lock, rollback journal은
  다시 추가하지 않는다.
- 런타임은 표준 라이브러리 기반 생성기·검증기와 Markdown reference만 유지한다.
