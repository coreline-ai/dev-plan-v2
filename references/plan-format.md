# v1-plus 개발 계획 형식

계획은 범위·진행·검증·재개 정보를 담는 Markdown 작업 계약이다. 별도 상태 DB나
증빙 스키마는 사용하지 않지만, v1의 Phase 규약을 줄이지 않는다.

## 상단 필수 섹션

1. 개발 목적
2. 개발 범위
3. 제외 범위
4. 참조 문서
5. 공통 진행 규칙
6. 실행 상태 및 모델 라우팅
7. Phase 상태 요약
8. QA 관점

`실행 상태`는 `DRAFT`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE` 중 하나다. Lead만
이를 바꾼다. 모델 라우팅에는 Lead Sol/high, ROUTINE Terra/medium, COMPLEX Luna/high,
새 QA Sol/high의 실제 requested/actual 모델을 실행 시 기록한다.

## Phase 형식

```markdown
## Phase 1. 인증 오류 처리
### 목표
- 만료 토큰 오류를 명확히 반환한다.

### 예상 변경 파일 / 영향 범위
- src/auth/session.py

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

Phase 상태 요약에는 모든 Phase의 완료 체크를 순서대로 둔다. QA 관점에는 실패 케이스,
경계값, 회귀 위험, 실제 QA 모델·판정을 체크리스트로 기록한다.
