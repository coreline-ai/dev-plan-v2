# dev-plan-v2 프로젝트 개요

작성 일시: `2026-07-25 KST`  
최종 갱신: `2026-07-25 KST`

## 1. 프로젝트 목적

현재 저장소를 `codex-dev-plan-orchestrator` 스킬의 원본 소스로 사용한다. 기존
`dev-plan-generator`의 경량 계획 생성 기능을 계승하되, Codex 계정 인증과 런타임이
제공하는 내장 에이전트 위임 기능만 사용하여 다음 전 과정을 지원한다.

1. 실행 가능한 개발계획 v2 생성
2. 기존 개발계획 v1 검증 및 v2 신규 문서로 업그레이드
3. Lead Sol의 작업 분해, 충돌 분석, Worker 라우팅
4. 사용 가능한 Worker의 구현과 자체 테스트
5. 새로운 Independent QA Sol의 독립 검증
6. 실패 시 제한된 재작업 배정
7. 계획·Phase·태스크·QA 상태의 결정적 갱신
8. 최종 통합 QA와 Lead Sol 최종 승인

## 2. 저장소와 배포 위치

| 구분 | 경로 또는 값 |
|---|---|
| 원본 Git 저장소 | `/Volumes/Eprojects/project_202607/dev-plan-v2` |
| 기본 브랜치 | `main` |
| 스킬 이름 | `codex-dev-plan-orchestrator` |
| 표시 이름 | `Codex 개발계획·구현·QA 오케스트레이터` |
| 설치 폴더명 | `codex-dev-plan-orchestrator` |
| 기존 스킬 원본 | `/Users/hwanchoi/.codex/skills/dev-plan-generator` |

현재 저장소 루트를 개발 원본으로 사용한다. 설치할 때는 검증된 배포 대상 파일만
`${CODEX_HOME:-$HOME/.codex}/skills/codex-dev-plan-orchestrator/`에 복사한다. 저장소
폴더명 `dev-plan-v2`와 설치 폴더명은 달라도 되지만, 설치 폴더명은 스킬 이름과
일치해야 한다.

기존 `dev-plan-generator`는 수정·덮어쓰기·자동 마이그레이션하지 않는다.

## 3. 핵심 원칙

- OpenAI API를 직접 호출하지 않는다.
- 별도의 Codex CLI 또는 중첩 Codex 프로세스를 실행하지 않는다.
- 런타임이 제공하는 내장 에이전트 위임 도구만 사용한다.
- 계획 문서를 요구사항·범위·실행 상태의 단일 기준으로 사용한다.
- 실행 증빙은 별도 evidence 디렉터리에 저장하고 계획에서 상대 경로로 참조한다.
- Lead Sol만 계획 상태를 변경하고 Phase 및 전체 계획을 승인한다.
- Worker는 계약에 허용된 경로만 수정하고 계획 문서를 수정하지 않는다.
- Independent QA Sol은 새 컨텍스트에서 검증하며 코드와 계획을 수정하지 않는다.
- QA `PASS` 전에는 Phase 또는 전체 계획을 완료 처리하지 않는다.
- 작업 범위가 변경되면 현재 계획을 임의 확장하지 않고 새 계획을 생성한다.
- 모델이나 도구의 존재를 가정하지 않고 실행 시 런타임에서 확인한다.

## 4. 지원 모드와 부작용

| 모드 | 역할 | 코드 수정 | Worker 위임 |
|---|---|---:|---:|
| `PLAN` | 실행 가능한 v2 계획 생성 | 금지 | 금지 |
| `UPGRADE` | v1을 보존하고 v2 신규 문서 생성 | 금지 | 금지 |
| `VALIDATE` | 구조 또는 실행 가능성 검사 | 금지 | 금지 |
| `EXECUTE` | 검증된 미완료 태스크 구현 | 허용 | 허용 |
| `RESUME` | 실제 상태 대조 후 미완료 지점부터 재개 | 허용 | 허용 |
| `QA` | Independent QA만 수행 | 금지 | QA만 생성 |
| `STATUS` | 계획·태스크·QA 상태 보고 | 금지 | 금지 |

명시적인 `EXECUTE` 또는 `RESUME` 요청이 없으면 제품 코드를 수정하거나 Worker를
생성하지 않는다. `QA`는 테스트 과정에서 생성되는 일반 산출물을 제외하고 소스 및
계획 파일을 변경하지 않는다.

## 5. 기존 v1 형식과의 관계

기존 형식에서 유지할 요소:

- `implement_YYYYMMDD_HHMMSS.md` 파일명
- 목적·범위·제외 범위·참조 문서
- 순서가 있는 Phase와 체크박스
- Phase별 자체 테스트
- QA 관점과 이슈 기록

v2에서 추가할 요소:

- 고유 Plan/Phase/DEV/TEST/QA ID
- 예상 변경 경로와 경로 소유권
- 태스크 의존성 및 병렬 실행 가능 여부
- 라우팅 복잡도와 런타임 enum에서 선택한 exact 모델 식별자
- 구체적인 완료 기준과 검증 명령
- planning revision, execution baseline, attempt별 input/output state, diff 및 실행 증빙
- Independent QA 게이트와 재작업 횟수
- 최종 통합 QA와 Lead 승인

## 6. 확정된 설계 결정

| 항목 | 결정 |
|---|---|
| 저장소 역할 | 원본 소스의 단일 기준 |
| Git 기본 브랜치 | `main` |
| 스킬 소스 배치 | 저장소 루트 |
| 설치 폴더 | `codex-dev-plan-orchestrator` |
| 기존 스킬 | 읽기 전용 참조, 무변경 |
| 상태 정본 | v2 Markdown 계획 문서 |
| 실행 증빙 | `dev-plan/evidence/<plan-id>/...` |
| Lead와 QA | 런타임이 제공하는 Sol |
| 일반 Worker | 런타임이 제공하는 Terra |
| 복잡 Worker | Luna가 실제 제공될 때만 사용 |
| Luna 부재 | 현재 계획 `BLOCKED`, 범위 보존 replacement 계획에서 Terra-safe 분할 |
| 현재 실행자가 Sol이 아님/불명 | 새 Sol Lead 생성, 불가능하면 상태 변경 모드 `BLOCKED` |
| QA 컨텍스트 | 신규 에이전트, 최소 문맥, 이전 판정 미전달 |
| Worker/QA 작업공간 | 태스크·attempt별 disposable worktree 또는 snapshot |
| QA 무수정 검증 | 전체 보호 manifest 전후 비교, 원본 작업공간 직접 수정 금지 |
| 상태 쓰기 | 이벤트, digest CAS, 잠금, fsync, 검증, 원자적 교체 |
| 재작업 한도 | 계획 메타데이터의 `max_rework`, 기본 2 |

## 7. 현재 환경 해석

현재 확인된 모델은 `gpt-5.6-sol`과 `gpt-5.6-terra`다. Luna 식별자는 확인되지
않았으므로 구현과 테스트에서 Luna를 존재하는 것처럼 호출하면 안 된다.

현재 위임 도구는 per-agent writable-root를 강제하지 않고 작업공간을 공유한다.
따라서 현재 환경의 기본은 `MANIFEST_GUARDED`다. 이 모드는 협력적 에이전트의
범위 이탈을 전후 manifest로 탐지하며 악의적 에이전트에 대한 보안 sandbox는 범위
밖이다. 필수 무결성 보호 장치를 만들 수 없으면 실행을 `BLOCKED`한다.

계획 문서는 논리 역할과 exact requested model을 분리해 기록한다.

- `worker_tier`: `TERRA`, `LUNA`, `UNASSIGNED`
- `assigned_model`: 런타임 enum에 존재하고 spawn에 성공한 exact requested model
  식별자 또는 `UNASSIGNED`

## 8. 구현 상태

설계 착수 기준을 충족한 뒤 다음 원본 구현을 완료했다.

- skill-creator 기반 `SKILL.md`와 `agents/openai.yaml`
- 공통 AST/YAML parser, canonical serializer, 생성기
- v1 보존 업그레이드
- structural/executable 검증
- allowlisted event state engine
- rejected event clone transaction, digest/version CAS, persistent `flock`, history,
  원자적 교체
- 제한 경로·command digest·evidence 검증
- disposable workspace, Phase-derived allowlist, aggregate provenance, rollback/commit marker
- planning/execution/finding을 포함한 최종 evidence graph 재검증
- 런타임 allowlist 패키징과 quick validation
- 생성·검증·상태 전이·업그레이드·패키징 pytest

런타임 규격의 단일 정본은 `references/`이며 `docs/02~04`는 정본 링크와 구현
요약만 유지한다. 상세 구현 후 재검증 결과는
`docs/07-expert-revalidation.md`에 누적한다.

전역 스킬 폴더 설치와 실제 사용자 프로젝트 Worker 실행은 이 원본 구현의 별도
배포·운영 단계다.
