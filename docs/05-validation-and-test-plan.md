# 검증 계획

## 자동 검증

- V2 전용 파일명·상단 섹션·Phase 형식
- 최소 두 Workstream, 비중복 허용 경로, 테스트, dependency와 Wave 정합성
- COMMON Wave 0, INTEGRATION 마지막 Wave, scope unit 단 한 번 배정
- 한 worktree의 own/cross-lane/unowned/ambiguous changed-file 결과
- `--previous-plan` 이력 연결, V1/V2 출력 경로 분리, 패키지 allowlist·링크

## Codex host smoke

자동 테스트와 분리해 실제 Codex 호스트에서 Sol Lead, Terra Worker, 새 Sol QA, worktree, host actual model ID를 확인한다. 결과는 실제 성공 또는 정직한 `BLOCKED`만 기록한다.
