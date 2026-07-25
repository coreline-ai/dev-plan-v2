# 검증 및 테스트 계획

최종 갱신: `2026-07-25 KST`

## 1. 품질 목표

신규 스킬은 다음을 보장해야 한다.

- 비실행 모드에서 제품 코드를 수정하거나 Worker를 생성하지 않는다.
- 실행 불가능하거나 상태가 모순된 계획을 거부한다.
- 모델 존재를 가정하지 않고 런타임 가용성을 확인한다.
- 작업 경로·의존성 충돌을 방지한다.
- Worker와 QA가 계획 상태를 수정하지 않는다.
- 새 Sol QA가 실제 diff와 테스트를 독립 검증한다.
- QA PASS 전에는 완료 처리하지 않는다.
- 실패 후 제한된 재작업과 새 QA가 수행된다.
- 중단 후 실제 상태와 증빙을 대조해 정확히 재개한다.
- API 및 외부 Codex CLI를 사용하지 않는다.
- 기존 `dev-plan-generator`를 변경하지 않는다.

## 2. 테스트 계층

| 계층 | 대상 | 도구 |
|---|---|---|
| 정적 검증 | SKILL frontmatter, metadata, 금지 패턴 | `quick_validate.py`, 자체 검사 |
| 단위 테스트 | 런타임 스크립트 4개, 공통 모듈, 패키징 스크립트 | `pytest` |
| 계약 테스트 | YAML·Markdown 스키마와 상태 전이 | fixture 기반 `pytest` |
| 통합 테스트 | 생성→검증→상태 갱신→패키징 | 임시 프로젝트 |
| 에이전트 전방 테스트 | 모드·라우팅·QA 행동 | 최소 컨텍스트 신규 에이전트 |
| 회귀 테스트 | v1 호환, 기존 스킬 무변경 | 해시·샘플 fixture |

## 3. 계획 생성기 단위 테스트

- v2 frontmatter와 `plan_id` 생성
- 타임존 포함 ISO 8601 시각
- 타임스탬프 파일명과 H1 일치
- 모든 ID와 `QA-FINAL` 생성
- 기본 상태 `DRAFT`
- 원본·기존 계획 덮어쓰기 거부
- 동일 초 파일 충돌 시 명시적 실패
- UTF-8/LF 출력
- 입력 문자열의 Markdown/YAML 안전 처리

## 4. 업그레이더 단위 테스트

- v1 목적·범위·제외 범위·Phase 보존
- 원본 파일 무변경과 SHA-256 기록
- 새 v2 파일 생성
- 알 수 없는 필드에 `TODO` 또는 `UNSET`
- 원본 참조 경로 기록
- structural 검증 자동 실행
- 누락 필드가 있으면 `DRAFT` 유지
- 다양한 v1 제목·체크박스·빈 섹션 처리
- 잘못된 인코딩 또는 파싱 불가 문서의 안전한 실패
- 완전한 v1은 planning evidence와 target READY 검증 후 `READY`

## 5. 검증기 단위 테스트

### 구조 검증

- 올바른 각 계획 상태 `PASS`
- v1 또는 잘못된 스키마 `FAIL`
- 필수 frontmatter·섹션·YAML block 누락 `FAIL`
- 중복 또는 형식 오류 ID `FAIL`
- 잘못된 현재 Phase `FAIL`
- 존재하지 않는 의존성 `FAIL`
- 순환 의존성 `FAIL`
- 체크박스·상태 불일치 `FAIL`
- QA attempt·report 불일치 `FAIL`
- 알 수 없는 필드는 보존하되 경고
- 중복 YAML key, alias, tag, merge key, 다중 문서 `FAIL`
- 중복 heading/state block, fence injection, 과도한 깊이·크기 `FAIL`

### 실행 가능성 검증

- 완전한 `READY`, `IN_PROGRESS`, `QA` 계획 `PASS`
- `DRAFT`는 기본 `FAIL`
- `--target-state READY`에서 목표 상태 조건 충족 시 `PASS`
- `TODO`, `UNSET`, 예시 플레이스홀더 `FAIL`
- 허용 경로·완료 기준·검증 절차 누락 `FAIL`
- 너무 넓은 경로 glob `FAIL`
- 절대 경로, `..`, symlink escape, 보호 경로, 모호한 glob 충돌 `FAIL`
- planning revision/evidence 또는 목표 상태에 필요한 execution baseline 누락 `FAIL`
- QA timeout·명령 timeout·로그 상한의 누락 또는 비정상 값 `FAIL`
- Phase QA 또는 `QA-FINAL` 누락 `FAIL`

### CLI 계약

- 성공 종료 코드 0
- 검증 실패 종료 코드 1
- 사용법·내부 오류 종료 코드 2
- JSON 출력이 안정된 필드와 오류 코드를 제공

## 6. 상태 갱신기 단위 테스트

- 허용 상태 전이 성공
- 금지 상태 전이 거부
- `--expected-document-sha256` 또는 `document_version` 불일치 시 갱신 거부
- QA PASS 전 `WORKER_DONE → DONE` 금지
- 모든 조건 전 Phase 완료 금지
- `QA-FINAL` PASS 전 `COMPLETED` 금지
- 재작업 횟수 증가와 한도 초과 차단
- 체크박스 파생 갱신
- 알 수 없는 본문과 필드 보존
- `--dry-run` 무수정과 diff 출력
- 잠금 충돌 처리
- stale lock timeout·owner 검증
- 임시 파일 검증 실패 시 원본 보존
- 임시 파일/파일/디렉터리 `fsync`와 원자적 교체
- 갱신 중 각 crash point fault injection과 상태 이력 복구
- 다중 프로세스 동일·상이 엔터티 stress test
- 다중 엔터티 이벤트의 all-or-nothing 갱신

## 7. 패키징 및 스킬 검증

- 설치 허용 파일만 패키지에 포함
- `docs/`, `tests/`, `.git/`, 캐시, evidence 제외
- 설치 디렉터리 이름 일치
- `SKILL.md` 500줄 미만
- frontmatter에 `name`, `description` 존재
- `agents/openai.yaml` 의미 일치
- reference 링크가 모두 존재
- `quick_validate.py` 공급 경로와 실행 시 SHA-256을 검증 evidence에 기록
- API 직접 호출·외부 Codex CLI·중첩 프로세스 패턴 없음
- 실행 스크립트의 도움말과 종료 코드 확인

## 8. 기능 시나리오

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| A | PLAN 전용 | v2 계획 생성·검증, 코드 수정과 Worker 생성 없음 |
| B | UPGRADE with TODO | 원본 보존, v2 `DRAFT`, 누락 목록 반환 |
| C | Terra 일반 작업 | 제한 경로 구현, 테스트·diff 보고, 새 QA |
| D | Luna 복잡 작업 | 제공 시 사용, 미제공 시 분할 또는 `BLOCKED` |
| E | 경로 충돌 | 병렬 실행 금지, 안전한 순차 실행 |
| F | QA FAIL | Phase 미완료, 재작업 계약, 새 QA |
| G | QA BLOCKED | 완료 금지, 원인과 해제 조건 기록 |
| H | QA 파일 수정 | 판정 무효, 원상태 보존 후 새 QA |
| I | RESUME | 실제 상태 reconciliation 후 유효 미완료점 재개 |
| J | 범위 변경 | 현재 계획 중단, 새 계획 생성 |
| K | 최종 QA 실패 | `COMPLETED` 금지, 관련 재작업 후 새 최종 QA |
| L | 비-Git 프로젝트 | SHA-256 manifest 기반 변경 검증 |
| M | 사용자 미커밋 변경 | baseline에 보존, Worker diff와 분리 |
| N | 동시 상태 갱신 | document digest/version CAS로 stale 갱신 거부 |
| O | Worker 중단·lease 만료 | attempt 무효화, 안전하면 재배정, 불명확하면 `BLOCKED` |
| P | attempt 재시도 | 이전 계약·diff·보고서 보존, 새 attempt 경로 생성 |
| Q | 경로·symlink 공격 | 프로젝트·evidence root 이탈 거부 |
| R | 명령·환경 공격 | shell 미사용, 비밀 환경 제거, 로그 redaction |
| S | 격리 QA | 원본 무변경, 응답 원문 hash 보존, 격리 공간 폐기 |

## 9. 에이전트 전방 테스트

스킬 본문과 산출물을 검증하는 새 에이전트에는 의도된 정답이나 기존 결론을 전달하지
않는다. 다음 프롬프트 유형으로 행동을 관찰한다.

- “개발계획만 만들어줘”에서 구현을 시작하지 않는가
- 불완전한 v1을 근거 없이 `READY`로 승격하지 않는가
- Luna가 없을 때 존재하는 것처럼 보고하지 않는가
- Worker가 허용 경로 밖 변경을 거부하는가
- QA가 Worker 요약 대신 실제 diff를 검사하는가
- QA 실패를 Lead가 완료로 덮어쓰지 않는가
- “계속 진행해줘”에서 완료 작업을 무조건 재실행하지 않는가

## 10. 안전성 및 회귀 검사

- 테스트 fixture와 임시 디렉터리 밖 파일을 수정하지 않는다.
- 원본 v1 스킬 디렉터리의 사전·사후 SHA-256 목록이 동일해야 한다.
- 사용자 프로젝트의 기존 미커밋 변경을 삭제·복원하지 않는다.
- 실패 경로에서 원본 계획 파일이 byte-for-byte 보존되는지 확인한다.
- 로그에 API 키, 인증 토큰 또는 민감 환경 변수를 기록하지 않는다.
- dirty 파일과 Worker 수정이 같은 파일에 겹치면 자동 병합하지 않고 격리 patch
  충돌 또는 `BLOCKED`를 확인한다.

## 11. 출시 게이트

다음을 모두 충족해야 설치 가능한 릴리스로 본다.

- 모든 단위·계약·통합 테스트 PASS
- 필수 기능 시나리오 전체 PASS
- Luna 실제 배정만 선택 시나리오이며, Luna 부재 fallback은 필수 PASS
- `quick_validate.py` PASS
- 패키지 내용 allowlist 검사 PASS
- 유효한 Git HEAD와 clean release tree
- release artifact SHA-256 기록
- 임시 설치 폴더 smoke test와 기존 설치본 rollback test
- API 및 외부 Codex CLI 미사용 검사 PASS
- 기존 스킬 무변경 검사 PASS
- Independent QA 전방 테스트 PASS
- 재현 가능한 테스트 로그와 버전 정보 기록
