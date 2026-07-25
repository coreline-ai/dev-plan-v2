# 간단한 실행 흐름

## PLAN

프로젝트를 읽고 작은 Phase로 나눈 뒤 계획을 만든다. 계획 생성 뒤 형식 검사만 한다.

## EXECUTE

1. 명시적 실행 요청과 최신 계획을 확인한다.
2. 첫 미완료 Phase의 범위와 테스트를 확인한다.
3. 필요할 때만 native Codex Worker에게 하나의 독립 작업을 위임한다.
4. Lead가 diff와 테스트 결과를 확인한다.
5. 확인한 체크리스트와 실행 기록만 갱신한다.

Worker 보고에는 변경 파일, 실행한 테스트, 결과, 미해결 위험을 요구한다. 별도
attestation·evidence manifest·worktree protocol은 만들지 않는다.

## QA

새 컨텍스트의 QA에게 diff, 변경 파일, 테스트 결과, 완료 기준을 준다. QA는 `PASS`,
`FIX`, `BLOCKED` 중 하나를 반환한다. `FIX`와 `BLOCKED`는 완료가 아니다.

## RESUME

계획 체크와 Git diff, 마지막 테스트 결과를 확인한다. 확인 가능한 첫 미완료 항목부터
재개한다. 상태가 불명확하면 추정하지 말고 사용자에게 확인한다.
