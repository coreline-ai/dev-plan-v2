# 검증 계획

## 자동 검증

- 계획 생성 후 필수 섹션·Phase·Worker 배정·체크리스트 검사
- Phase 상태 요약과 Phase 순서 일치 검사
- `--ready`에서 실제 런타임 목록, exact requested ID, Sol/Terra/Luna 역할, `fork_turns: none` 검사
- Luna 없는 COMPLEX Phase 거부
- `--complete`에서 requested=host actual, 실제 테스트/Worker 보고, QA PASS, 전체 완료 검사
- 기존 계획 덮어쓰기 거부
- 패키지 allowlist와 내부 링크 검사

## 운영 smoke

실제 프로젝트에서 한 번은 다음을 확인한다.

1. 런타임이 모델 목록과 Lead/Worker/QA 생성 뒤 actual ID를 노출하는지 확인
2. Sol Lead, Terra Worker, 새 Sol QA를 각각 exact override와 `fork_turns: none`으로 생성
3. disposable 또는 제한된 작업공간에서 한 책임 단위 구현
4. Lead diff/테스트 재확인과 QA PASS/FIX/BLOCKED 기록
5. Luna가 없는 COMPLEX 작업이 BLOCKED 또는 재분해되는지 확인
6. `--complete`가 모델 기록 누락·불일치를 거부하는지 확인
