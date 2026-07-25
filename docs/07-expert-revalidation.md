# 전문가 재검증 보고서

검증 일시: `2026-07-25 KST`  
검증 대상: `/Volumes/Eprojects/project_202607/dev-plan-v2`  
기준 브랜치: `main`  
설치 스킬 이름: `codex-dev-plan-orchestrator`

## 1. 최종 판정

**RELEASE-READY — 설치 가능한 원본 스킬**

현재 저장소 루트는 스킬의 canonical 원본 소스다. 생성·업그레이드·검증·상태 전이,
작업공간 통합·복구, 패키징 도구와 런타임 references가 구현됐고 자동 검증을
통과했다. 이 판정은 저장소 원본과 임시 설치 패키지에 대한 것이다.

전역 `${CODEX_HOME}/skills` 설치와 실제 외부 사용자 프로젝트에서의 Worker/QA
운영 파일럿은 수행하지 않았다. 따라서 특정 외부 프로젝트 실행까지 검증됐다고
확대 해석하지 않는다.

## 2. 구현 범위

| 영역 | 구현 결과 |
|---|---|
| 스킬 진입점 | `SKILL.md`, 7개 모드, 부작용 경계, Lead/Worker/QA 역할 |
| UI metadata | `agents/openai.yaml`, mode-first 기본 프롬프트 |
| 계획 문서 | `codex-dev-plan/v2` AST parser, 제한 YAML, canonical serializer |
| 생성·변환 | 신규 DRAFT 생성, v1 원본 보존 v2 업그레이드 |
| 검증 | structural/executable/candidate-event 검증 |
| 상태 엔진 | allowlisted event, rejected-event clone transaction, 파생 체크박스 |
| 동시성 | SHA-256/version CAS, persistent POSIX `flock`, state history, 원자 교체 |
| 증빙 | attempt INPUT/RESULT, runtime/approval attestation, recursive hash 검증 |
| 작업공간 | snapshot, disposable copy, 범위 검증, source CAS 통합, rollback |
| 승인 트랜잭션 | source→evidence→plan lock, COMMITTING/COMMITTED marker, 보상 복구 |
| provenance | Worker→TEST→Phase aggregate→QA→source state 연결 |
| 패키징 | 14개 runtime 파일 allowlist, 내부 링크·quick validation, 결정적 manifest |

## 3. 고위험 재검증과 보완

독립 스키마 감사에서 발견된 고위험 후보를 구현과 회귀 테스트로 해소했다.

| 위험 | 보완 |
|---|---|
| 거부 이벤트가 문서를 부분 변경 | deep-clone에 전체 event 적용 후 성공 시에만 commit |
| 시작 후 만료된 Worker lease 보고 수락 | `WORKER_REPORTED`에서 lease 재검사 |
| Worker state와 무관한 Phase QA | 상태 graph 도달성 또는 소유 경로 inventory 일치 검증 |
| stale lock ABA·부분 owner JSON 영구 차단 | unlink 회수 제거, persistent inode `flock` |
| source/evidence/plan TOCTOU | 고정 lock order와 잠금 내부 재해시·재파싱 |
| 통합 CLI allowlist 임의 확대 | Phase DEV path union 파생, exact 대조, journal digest |
| 통합 중 Plan contract 변경 | source→evidence→plan lock 안에서 SHA/version/contract 재검사 |
| READY/EXECUTION baseline race | 두 이벤트도 source lock 안에서 current-state 재검증 |
| 최종 evidence 일부 누락·변조 | baseline, Phase, final QA, finding, resolution, risk graph 재검증 |
| self-authored model/spawn attestation | 별도 enum snapshot·spawn receipt file hash와 교차 결합 |
| 다른 workspace manifest로 격리 우회 | event·attestation·INPUT/RESULT workspace root/ID 일치 검증 |
| source 내부 workspace로 원본 직접 작업 | canonical root 외부성 검사와 root SHA-256 기반 ID 재계산 |
| QA 이전 source 통합 | Phase/DEV/TEST/QA readiness와 aggregate=QA input gate |
| package manifest 환경 의존 | source/destination 절대 경로를 manifest에서 제거 |

독립 스키마·상태·런타임 재감사 결과는 모두 **잔여 BLOCKER/HIGH 없음**이다.

## 4. 자동 검증 결과

| 검사 | 결과 |
|---|---|
| Python 3.11 compile | PASS |
| pytest | PASS, `33 passed` |
| `git diff --check` | PASS |
| skill-creator `quick_validate.py` | PASS, `Skill is valid!` |
| runtime preflight | PASS, Python `3.11.14`, POSIX flock, PyYAML `6.0.3`, markdown-it-py `4.0.0` |
| package allowlist | PASS, runtime 파일 14개 |
| package 내부 Markdown 링크 | PASS |
| packaged CLI 도움말 | PASS, 5개 command CLI |
| packaged runtime preflight | PASS |
| packaged 생성→structural validate smoke | PASS |
| 의존성 없는 Python 3.11 venv | PASS, traceback 없이 종료 코드 1과 설치 안내 |
| 금지 API·외부 Codex CLI·`shell=True` 패턴 | PASS, 발견 없음 |
| 기존 `dev-plan-generator` 기준 hash | PASS, 모두 동일 |

`pytest`는 생성·업그레이드·검증·상태 전이·경로 계약·lease·evidence schema·실제
Phase 승인 통합·rollback·commit marker·lock crash recovery·패키지 결정성을
임시 프로젝트에서 검증한다.

## 5. 패키지 검증 기록

| 항목 | 값 |
|---|---|
| 임시 패키지 | `/tmp/codex-dev-plan-release-final4.OgBFP3/codex-dev-plan-orchestrator` |
| manifest | `/tmp/codex-dev-plan-release-final4.OgBFP3/codex-dev-plan-orchestrator.manifest.json` |
| manifest SHA-256 | `5630e9bfc214036baf5906d1cecd2cb94a1734f243cb8aea0e1059cf9370fcb0` |
| validator SHA-256 | `6cc9dc3199c935916cf6f73fcbbbb0e3bb1b58c8f5109fefa499978908164f51` |
| quick validation | `Skill is valid!` |

manifest는 `codex-skill-package-manifest/v1`이며 출력 위치와 무관한 content
manifest다. 임시 패키지는 전역 설치 폴더를 변경하지 않는다.

## 6. 기존 스킬 무변경

| 파일 | SHA-256 |
|---|---|
| `.repo-version` | `fff799cd21da73228f7982d6bd0963996b520d835138102660727b09bb7fad28` |
| `SKILL.md` | `05c7a540337a7cd74bf9e872c29c6fe036a51f7247ff9c25a67d62e38c447182` |
| `agents/openai.yaml` | `f5e280b8b601b1f508fd71781e3a31f740eda221a5bd713e2bd527366e7cc54a` |
| `scripts/new_dev_plan.py` | `ad814a449c2fedc53b320209e0fe4c46c64b17c283ac2a53be9e5465335b17bb` |

검증 대상은 `/Users/hwanchoi/.codex/skills/dev-plan-generator`이며 신규 원본
저장소 구현 과정에서 수정하지 않았다.

## 7. release 경계와 운영 게이트

- 이 스킬의 잠금 구현은 POSIX `fcntl.flock`이 있는 런타임을 요구한다.
- 현재 확인된 Worker tier는 Terra이며 Luna는 확인되지 않았다. Luna가 없으면
  존재한다고 가정하지 않고 replacement 계획 또는 `BLOCKED` 정책을 따른다.
- `MANIFEST_GUARDED`는 협력적 에이전트의 범위 이탈·오염을 탐지하는 무결성 모델이지
  hostile sandbox가 아니다.
- 실제 설치 후에는 `docs/05-validation-and-test-plan.md` §11.2의 운영 파일럿을
  별도로 수행한다.
- release commit은 이 보고서를 포함하는 `main` HEAD이며 최종 전달 시 exact commit
  SHA와 clean tree를 함께 확인한다.
