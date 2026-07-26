# 필수 개발 계획 형식

계획은 범위·진행·검증·재개·모델 배정을 담는 Markdown 작업 계약이다. 별도 상태 DB나
증빙 스키마는 쓰지 않는다.

## 상단 필수 섹션

1. 개발 목적
2. 개발 범위
3. 제외 범위
4. 참조 문서
5. 공통 진행 규칙
6. 실행 상태 및 모델 라우팅
7. Phase 상태 요약
8. QA 관점
9. 실행 기록

`실행 상태`는 `DRAFT`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE` 중 하나이며 Lead만
바꾼다. `DRAFT`에서는 미확인 값을 둘 수 있지만, `READY`부터는 아래 값이 필수다.

```markdown
## 실행 상태 및 모델 라우팅
- 계획 상태: READY
- 현재 Phase: Phase 1
- 확인된 런타임 모델: gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
- Lead requested model: gpt-5.6-sol
- Lead actual model: PENDING
- Lead context: fork_turns: none
- QA requested model: gpt-5.6-sol
- QA actual model: PENDING
- QA context: fork_turns: none
- QA verdict: PENDING
```

`확인된 런타임 모델`은 실행 시점에 host가 제공한 정확한 목록이다. requested ID는 이 목록에
정확히 있어야 한다. `actual model`은 생성 뒤 host가 반환한 값을 추정 없이 기록한다.

## Phase 형식

```markdown
## Phase 1. 인증 오류 처리
### 목표
- 만료 토큰 오류를 명확히 반환한다.

### Worker 배정
- 작업 등급: ROUTINE
- requested model: gpt-5.6-terra
- actual model: PENDING
- context: fork_turns: none

### 구현 태스크
- [ ] 오류 분기 구현

### 자체 테스트
- [ ] python3.11 -m pytest tests/auth

### 이슈 및 수정
- [ ] 발견 이슈 없음

### 완료 조건
- [ ] 구현 태스크 완료
- [ ] 자체 테스트 완료
- [ ] Lead가 diff와 범위를 확인
- [ ] 다음 Phase 진행 가능
```

`ROUTINE`은 Terra만, `COMPLEX`는 Luna만 요청한다. Luna가 없으면 Terra로 대체하지 말고
`BLOCKED` 또는 Terra-safe Phase로 재분해한다. Worker와 QA는 반드시 `fork_turns: none`
수준의 새 최소 컨텍스트다.

`DONE` 전에 actual 모델은 requested 모델과 정확히 일치해야 하고, 모든 Phase 완료,
실제 테스트·Worker 보고, 새 Sol QA의 `PASS`가 필요하다.
