# 전문가 재검증 보고서

검증 일시: `2026-07-25 KST`  
검증 대상: `/Volumes/Eprojects/project_202607/dev-plan-v2`  
기준 브랜치: `main`  
초기 문서 기준 커밋: `a1e842f48aa6dda85912291f77b33611e494d439`

## 1. 최종 판정

**READY — 스킬 구현 착수 가능**

이 판정은 `SKILL.md`, scripts, references, tests 구현을 시작할 수 있다는 뜻이다.
스킬 구현·테스트·패키징·전역 설치가 완료됐다는 뜻은 아니다.

## 2. 검증 범위

- 저장소 루트와 설치 패키지 역할 분리
- skill-creator 규격과 UI metadata 제약
- v2 Markdown/YAML 정규 문법
- 계획·Phase·DEV·TEST·QA 상태와 이벤트 전이
- planning revision과 execution baseline 생명주기
- attempt별 INPUT/RESULT evidence manifest
- Worker 라우팅, Luna 부재, native model enum
- Independent QA 신규 컨텍스트와 응답 보존
- 병렬 wave aggregate patch, CAS, rollback
- dirty Git·비-Git·공유 작업공간 무결성
- 경로·symlink·명령·환경변수·secret 보호
- 실패·차단·재작업·재개·최종 QA
- 테스트 시나리오와 출시 게이트

## 3. 주요 보완 결과

| 초기 문제 | 최종 결정 |
|---|---|
| `DRAFT`와 executable 검증 충돌 | `--candidate-event`와 `--target-state`로 분리 |
| planning/execution 기준 시점 혼동 | `planning_revision`과 `execution_baseline` 분리 |
| Markdown 부분 수정의 모호성 | AST/source span과 제한 YAML 정규 문법 |
| 상태 전이 누락 | 이벤트별 from·guard·payload·mutation·error contract |
| 최종 QA 재작업의 다중 Phase 충돌 | earliest affected Phase + downstream `REWORK_PENDING` |
| Worker/QA 유실 복구 불가 | `current_run`, lease/deadline, invalidation event |
| 테스트와 코드 상태 연결 부재 | `tested_state_id`, task refs, command digest |
| evidence 덮어쓰기 | attempt별 append-only INPUT/RESULT manifest |
| 병렬 patch 귀속 문제 | clean Git wave, integration worktree, aggregate patch |
| 상태 갱신 경쟁 | document digest/version CAS와 잠금 내부 재검증 |
| QA 수정 금지와 보고서 저장 주체 충돌 | QA 응답 반환, Lead 무변조 저장 |
| 공유 writable workspace 한계 | `MANIFEST_GUARDED` 협력적 무결성 모델 |
| 모델 제공 가정 | runtime enum + exact requested model, Luna 미지원 처리 |
| 경로·명령 삽입 위험 | 제한 matcher, realpath, argv, `shell=False`, env 최소화 |
| secret evidence 위험 | 로그 redaction, report/diff fail-closed |
| finding 해소 증명 부재 | qualified finding ledger와 승인 evidence |
| 기존 스킬 훼손 위험 | 읽기 전용 원본과 SHA-256 baseline |

## 4. 독립 검토 결과

의도된 결론을 전달하지 않은 별도 신규 컨텍스트에서 세 관점으로 재검증했다.

| 검토 관점 | 최종 판정 | 확인 결과 |
|---|---|---|
| 스키마·상태·파서 | `READY` | 구현 차단 스키마·전이·evidence 결함 없음 |
| Codex 런타임·Worker·QA | `READY` | 명시한 `MANIFEST_GUARDED` threat model에서 차단 결함 없음 |
| 문서 일관성·Git·테스트 | `READY` | BLOCKER/HIGH 결함 없음 |

## 5. 자동 정적 검사

| 검사 | 결과 |
|---|---|
| 모든 Markdown fence 닫힘 | PASS |
| 문서 내 YAML 예시 19개 파싱 | PASS |
| canonical Phase 예시의 entity state block 수 | PASS |
| `git diff --check` | PASS |
| `short_description` 25~64자 | PASS, 55자 |
| SKILL description 1,024자 이하 | PASS, 450자 |
| Git 기본 브랜치 | PASS, `main` |
| 유효한 Git HEAD | PASS |

실제 Python 스크립트와 테스트 파일은 아직 없으므로 단위·통합 테스트는 이 단계의
검증 범위가 아니다.

## 6. 기존 스킬 무변경 기준

| 파일 | SHA-256 |
|---|---|
| `.repo-version` | `fff799cd21da73228f7982d6bd0963996b520d835138102660727b09bb7fad28` |
| `SKILL.md` | `05c7a540337a7cd74bf9e872c29c6fe036a51f7247ff9c25a67d62e38c447182` |
| `agents/openai.yaml` | `f5e280b8b601b1f508fd71781e3a31f740eda221a5bd713e2bd527366e7cc54a` |
| `scripts/new_dev_plan.py` | `ad814a449c2fedc53b320209e0fe4c46c64b17c283ac2a53be9e5465335b17bb` |

구현·출시 검증 때 동일 목록을 다시 계산해 기존 스킬 무변경을 확인한다.

## 7. 명시적 잔여 제약

- 현재 제공 모델은 Sol과 Terra이며 Luna는 확인되지 않았다.
- 공유 작업공간의 `MANIFEST_GUARDED`는 협력적 에이전트의 실수·범위 이탈을 탐지하는
  무결성 모델이며 악의적 에이전트를 차단하는 보안 sandbox는 아니다.
- 런타임 의존성 버전과 실제 parser 구현은 Phase 1~3에서 테스트로 확정해야 한다.
- 전역 스킬 설치는 전체 출시 게이트 통과 후 별도 승인 하에 수행한다.

## 8. 구현 착수 권고

1. skill-creator `init_skill.py`를 임시 staging에서 실행한다.
2. 공통 Markdown AST·제한 YAML parser/model을 먼저 구현한다.
3. 생성기보다 validator와 event state engine의 fixture를 함께 만든다.
4. 상태 엔진이 안정된 뒤 Worker/QA 오케스트레이션을 연결한다.
5. `docs/05-validation-and-test-plan.md`의 필수 시나리오를 모두 자동화한다.
