# 계획 규약 재균형 기록

## 문제

초기 경량화는 workflow platform 코드를 제거하는 데는 성공했지만 v1의 범위·진행·자체
테스트·QA·재개 규약과, 가장 중요한 역할별 모델 라우팅까지 약화시켰다. 기본 세션 상속은
Sol Lead / Terra Worker / Luna Complex Worker / 새 Sol QA의 exact override를 대체하지 못한다.

## 보완

- 필수 Phase 템플릿과 Worker 배정 섹션 복원
- 실행 전 런타임 모델 목록과 exact requested ID 기록 추가
- Lead Sol, ROUTINE Terra, COMPLEX Luna, 독립 QA Sol을 fail-closed 게이트로 복원
- `fork_turns: none` 최소 컨텍스트와 host actual ID 기록 강제
- Luna 부재·actual ID 미노출·모델 불일치 시 BLOCKED/재분해
- `--ready`와 `--complete`로 preflight와 완료 기록을 분리 검증

추론 강도는 원본 핵심 계약이 아니므로 필수 게이트로 만들지 않는다. 런타임에서 별도
설정했을 때만 사실대로 기록한다.

## 유지한 경량화

- event state machine, evidence manifest, workspace ID, 다중 lock, rollback journal은
  다시 추가하지 않는다.
- 런타임은 표준 라이브러리 기반 생성기·검증기와 Markdown reference만 유지한다.
