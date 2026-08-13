# 검증 계획

## 자동 검증

- 직렬·COMMON 선행·병렬 안전성 판정과 사유
- JSON schema, 경로 소유권, dependency와 Wave
- JSON에서 렌더링한 Markdown의 일치
- clean Git baseline과 COMMON 이후 lane baseline
- tracked·staged·unstaged·untracked·delete·rename scope 결과
- 실행 ledger의 plan hash, commit, 테스트 종료 코드, 위험도별 QA
- V1/V2 출력 경로 분리와 패키지 allowlist

## 실제 smoke

- 의미적으로 결합된 요청이 직렬로 전환되는지 확인
- COMMON commit 이후 두 worktree가 같은 baseline에서 시작하는지 확인
- lane 위반이 통합 전에 차단되는지 확인
- 중단 후 ledger와 Git 상태로 재개 또는 정직한 차단이 되는지 확인
