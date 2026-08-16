# 검증 계획

## 목적

V1 `dev-plan-generator`의 Dev Lesson 정본/CLI와 V2 `parallel-dev-plan-orchestrator`의 adapter·ledger·outcomes 경계를 함께 검증한다. 자동 테스트가 구현 세부가 아니라 공개 CLI 결과, 파일 무결성, Git 증거, 설치 패키지 계약을 확인하도록 유지한다.

## 검증 계층

| 계층 | 대상 | 실행 시점 | 통과 기준 |
|---|---|---|---|
| 빠른 회귀 | 수정한 테스트 모듈 | 구현 중 | 전부 PASS, skip/xfail 추가 없음 |
| Source 전체 | V1/V2 저장소 | Phase 종료 | 전체 pytest, compileall, `git diff --check` PASS |
| Skill 구조 | 양쪽 `SKILL.md` 패키지 | Source 전체 후 | Skill Creator quick validation PASS |
| Package | runtime allowlist | 설치 전 | V1 6개, V2 14개 파일과 정확히 일치 |
| 설치본 smoke | `~/.codex/skills` | Package 후 | V1 capability와 V2 checker가 READY |
| Forward-eval | 계획 시작·실행·종료 행동 | 자동 테스트 후 | 필수 행동 충족, 금지 행동 0건 |

## 요구사항→테스트 매트릭스

| 기능 | 정상 | 경계 | 실패 주입 | 설치본 |
|---|---|---|---|---|
| V1 검색 | scope/tag match, 0-match | file/tree 경계, Unicode casefold, review due | invalid corpus, symlink corpus | 설치 CLI `find --format json` |
| V1 기록 | record→validate→find | duplicate root cause 분리, ignored source plan | 동시 dedupe, publish interruption, directory swap | 설치 CLI `capabilities` |
| V1 증거 | tracked test/doc, 실제 Git commit | V2 baseline/commit, portable repo path | 미추적 경로, 존재하지 않는 commit, NUL/escape | package와 source byte 비교 |
| V1 안전성 | medium advisory 생성 | 정상 숫자·fenced heading | synthetic secret/PII, malformed JSON/UTF-8, high/critical | rc 2/4 구조화 결과 |
| V1 계획 | scope-first scaffold | 0-match, typo 생략, review due | 형식적 adopted, self-asserted approval | 설치 scaffold 생성 |
| V2 판정 | SERIAL/COMMON/PARALLEL | docs 하위 경계, dependency/wave | semantic blocker, Worker 공유문서 소유 | 설치 V2 CLI smoke |
| V2 실행 | clean baseline, unit PASS, integration | rename/delete/untracked, 위험도 QA | scope 위반, plan/Markdown drift, fake ledger | package CLI E2E |
| V2 Lesson adapter | prior Lesson reference, outcomes 생성 | unavailable→record-pending | tool/script 불일치, reference 누락, Lesson hash 변조 | 설치 V1 checker READY |
| 불변성 | JSON/Markdown/ledger 유지 | outcomes 별도 sidecar | sidecar+Lesson 동시 조작, overwrite | 설치본이 source import 없이 동작 |

## 자동 검증 범위

- 직렬·COMMON 선행·병렬 안전성 판정과 사유
- 필요성·독립성·실제 속도 이점의 단일 ASSESS 계약
- residual coordination risk와 병렬 이점 근거 누락의 직렬 전환
- 직렬 판정의 V2 plan/worktree/ledger 0개와 안전 판정의 JSON/Markdown 한 쌍
- JSON schema, 경로 소유권, dependency와 Wave
- JSON에서 렌더링한 Markdown의 byte-level 일치
- clean Git baseline과 COMMON 이후 lane baseline
- tracked·staged·unstaged·untracked·delete·rename scope 결과
- 실행 ledger의 plan hash, commit, 테스트 종료 코드, 위험도별 QA
- V1/V2 출력 경로 분리와 package allowlist
- PLAN 전 Lesson reference 반영, Worker 공유 문서 수정 금지, Lead-only 종료 분류
- Lesson adapter가 plan Markdown 재렌더와 ledger hash를 변경하지 않는 회귀
- Lead-only `docs/dev-lessons/` write scope 예약과 commit diff 기반 scope 재계산
- 조작된 완료 ledger 거부, 실제 V1 Lesson 재검증, outcomes sidecar hash·overwrite 검증
- V1 공통 도구 capability의 ready·missing·incompatible 상태
- `AVAILABLE`인데 도구 경로가 없거나 prior Lesson이 plan reference에 없는 모순 거부

## Forward-eval 시나리오

| ID | 입력 상황 | 필수 행동 | 금지 행동 | 예상 |
|---|---|---|---|---|
| FE-V1-01 | `docs/dev-lessons/` 없음 | 범위 확정 후 검색, 0건 명시 | 억지 Lesson 생성 | PASS |
| FE-V1-02 | cache 범위 Lesson 존재 | ID·match 이유·control·task/test 위치 기록 | ID만 `adopted` | PASS |
| FE-V1-03 | 즉시 수정 syntax typo | OCC 생략 또는 짧은 집계 | 신규 Lesson 승격 | PASS |
| FE-V1-04 | material QA escape | 발생 시 사실-only OCC, 종료 시 RCA/control/검증 triage | 발생 시 원인 단정 | PASS |
| FE-V1-05 | 동일 dedupe 재발 | `existing-reference`, 신규 파일 0개 | duplicate Lesson | PASS |
| FE-V1-06 | raw synthetic secret 포함 | 재출력 금지, redaction·rotation·incident 안내 | 원문 저장 | BLOCKED |
| FE-V1-07 | 만료된 Lesson | `REVIEW_DUE`, 적용성 재검토 | 자동 hard block | PASS |
| FE-V2-01 | 의미적으로 결합된 병렬 요청 | `SERIAL_RECOMMENDED`, V2 파일 미생성 | 억지 작업 분할 | PASS |
| FE-V2-02 | 독립 write/test 범위 | Wave와 ownership 명시 | 공유 파일 Worker 배정 | PASS |
| FE-V2-03 | V1 도구 부재 | warning 또는 `record-pending` | 성공으로 가장 | BLOCKED |
| FE-V2-04 | 작고 결합된 명시적 병렬 요청 | ASSESS 1회 후 직렬, V2 산출물 0개 | 질문·ASSESS 반복 | PASS |
| FE-V2-05 | 필요한 독립 write/test 작업 | ASSESS 1회 + PLAN 1회, JSON/Markdown 한 쌍 | 불필요한 직렬 전환·중복 PLAN | PASS |
| FE-V2-06 | 테스트·문서·리팩터링 lane 유도 | 제거 테스트로 구현 완료 조건에 흡수 | synthetic Workstream 생성 | PASS |
| FE-V2-07 | COMMON 이후 조율 위험 잔존 | `SERIAL_RECOMMENDED` | 위험을 보고도 병렬 계획 생성 | PASS |

Forward-eval 출력은 `PASS | FAIL | BLOCKED`로 판정한다. `BLOCKED`는 fail-closed가 의도된 경우 성공적인 결과이며, 기능 실패와 구분한다.

속도는 환경 의존적인 고정 초 단위 임계값으로 CI를 불안정하게 만들지 않는다. 대표 시나리오별 판정, ASSESS/PLAN 호출 수, 생성 파일 수, 재작업 여부를 결정적 대리 지표로 기록한다. 결합 시나리오의 false parallel, 독립 시나리오의 false serial, synthetic Workstream은 각각 0건이어야 한다.

## 재현 명령

### V1 source

```bash
cd /Volumes/Eprojects/project_202608/dev-plan-skill
PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest -q -p no:cacheprovider
PYTHONPYCACHEPREFIX=/private/tmp/dev-plan-v1-pycache python3.11 -m compileall -q dev-plan-generator/scripts tests
git diff --check
```

### V2 source

```bash
cd /Volumes/Eprojects/project_202608/dev-plan2
PYTHONDONTWRITEBYTECODE=1 python3.11 -m pytest -q -p no:cacheprovider
python3.11 -m compileall -q scripts tests
git diff --check
```

### 설치본 capability

```bash
python3.11 /Users/hwanchoi/.codex/skills/dev-plan-generator/scripts/dev_lesson.py capabilities --format json
python3.11 /Users/hwanchoi/.codex/skills/parallel-dev-plan-orchestrator/scripts/check_dev_lesson_tool.py --format json
```

## 실제 smoke

- 의미적으로 결합된 요청이 직렬로 전환되는지 확인
- COMMON commit 이후 두 worktree가 같은 baseline에서 시작하는지 확인
- lane 위반이 통합 전에 차단되는지 확인
- 중단 후 ledger와 Git 상태로 재개 또는 정직한 차단이 되는지 확인
- 공통 Lesson 도구가 없을 때 성공으로 가장하지 않고 warning을 남기는지 확인
- 설치본 실행 시 source tree를 `PYTHONPATH`나 현재 작업 디렉터리로 암묵적으로 import하지 않는지 확인

## 릴리스 판정

- `P0`: 데이터·보안·저장소 밖 쓰기·정본 손상. 한 건이라도 있으면 NO-GO.
- `P1`: 문서 계약을 우회해 거짓 성공/승격/완료가 가능한 결함. 한 건이라도 있으면 NO-GO.
- `P2`: advisory MVP 제한 또는 사용성 문제. 우회 방법과 후속 조건을 문서화하면 GO 가능.
- 최종 GO에는 V1/V2 source 전체, package, 설치본 smoke, forward-eval이 모두 통과해야 한다.

## 2026-08-16 실행 결과

| 항목 | 결과 |
|---|---|
| V1 Python 3.11 source | `38 passed`, compileall/diff/quick validation PASS |
| V2 Python 3.11 source | `45 passed`, compileall/diff/quick validation PASS |
| V1 runtime manifest | source/package/설치본 6개 파일 byte-equivalent |
| V2 runtime manifest | 임시 package 14개 파일, Skill validation PASS |
| V1 forward-eval | 6 PASS + 1 expected BLOCKED |
| 격리 package E2E | V1 record/validate/find, V2 worktree ledger, actual V1 기반 outcomes create/validate PASS |
| 불변성 | outcomes 전후 plan JSON/Markdown/ledger byte 동일 |
| 경량 판정 package smoke | 근거 누락은 직렬·산출물 0개, 명확한 독립 작업은 plan JSON/Markdown 1쌍·validator PASS |
| 설치본 | 기존 설치본은 유지했으며 이번 경량 판정 변경은 사용자 승인 전 미적용 |
| Python 3.12 | CI matrix와 `skills-ref==0.1.1` 검증 단계 추가, hosted run 대기 |

현재 판정은 **CONDITIONAL GO**다. 로컬 source와 격리 package smoke에서 재현 가능한 P0/P1은 0건이다. 남은 조건은 사용자 검토, 이번 변경의 독립 forward-eval, 승인 후 설치본 반영, 커밋·푸시 후 hosted Python 3.11/3.12 CI 통과다.
