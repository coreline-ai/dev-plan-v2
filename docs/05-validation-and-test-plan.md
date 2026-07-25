# 검증 계획

## 자동 검증

- 계획 생성 후 v1-plus 필수 섹션·Phase·체크리스트 검사
- Phase 상태 요약과 Phase 순서 일치 검사
- 실행 상태와 Lead/Worker/QA 모델 라우팅 항목 검사
- `--ready`에서 placeholder·상태·테스트 불완전성 거부
- 기존 계획 덮어쓰기 거부
- 패키지 allowlist와 내부 링크 검사

## 운영 smoke

실제 프로젝트에서는 다음을 한 번 이상 확인한다.

1. Sol Lead 모델과 reasoning effort 기록
2. Terra Worker 또는 이용 가능한 Luna Worker의 명시적 배정
3. disposable 또는 제한된 작업공간에서 한 책임 단위 구현
4. Lead diff/테스트 재확인
5. 새 Sol QA의 PASS/FIX/BLOCKED 판정과 모델 기록
6. `RESUME`에서 미완료 Phase를 정확히 선택하는지 확인
