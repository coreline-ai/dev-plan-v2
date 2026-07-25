# 신규 스킬 아키텍처

최종 갱신: `2026-07-25 KST`

## 1. 저장소 구조

현재 Git 저장소 루트가 스킬의 원본 소스다.

```text
dev-plan-v2/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── new_dev_plan.py
│   ├── upgrade_dev_plan.py
│   ├── validate_dev_plan.py
│   ├── update_plan_state.py
│   └── package_skill.py
├── references/
│   ├── plan-schema-v2.md
│   ├── execution-workflow.md
│   └── agent-contracts.md
├── tests/
│   ├── fixtures/
│   ├── test_new_dev_plan.py
│   ├── test_upgrade_dev_plan.py
│   ├── test_validate_dev_plan.py
│   ├── test_update_plan_state.py
│   └── test_package_skill.py
├── docs/
│   └── 설계·개발·재검증 문서
├── pyproject.toml
└── .gitignore
```

설치 산출물에는 `SKILL.md`, `agents/openai.yaml`, 런타임용 스크립트 4개와 공통
모듈, `references/`, 런타임 의존성 메타데이터만 포함한다. 개발 전용
`package_skill.py`, `docs/`, `tests/`, Git 메타데이터와 개발 캐시는 제외한다.

## 2. 실행 아키텍처

```text
사용자 요청
  ↓
모드 판별
  ├─ PLAN / UPGRADE / VALIDATE / STATUS
  └─ EXECUTE / RESUME / QA
       ↓
Lead Sol
  ├─ 계획 구조 및 실행 가능성 검증
  ├─ planning/execution 상태·작업 경로·의존성 확인
  ├─ 좁은 작업 계약 생성
  ├─ 런타임 모델 검색과 Worker 라우팅
  ├─ 결과·증빙 수집 및 상태 갱신
  └─ Phase·최종 승인
       ↓
Terra 또는 실제 제공되는 Luna Worker
  ├─ 허용 경로 구현
  ├─ 자체 테스트
  └─ 구조화된 결과 보고
       ↓
새 Independent QA Sol
  ├─ 최소 컨텍스트
  ├─ 실제 계획·계약·diff·로그 검증
  ├─ 소스와 계획 수정 금지
  └─ PASS / FAIL / BLOCKED
```

## 3. 구성요소 책임

### `SKILL.md`

- 사용자 의도를 7개 모드 중 하나로 판별한다.
- 모드별 허용 부작용을 강제한다.
- 읽어야 할 reference 문서를 조건별로 안내한다.
- `EXECUTE`와 `RESUME` 전 `validate_dev_plan.py --level executable`을 강제한다.
- 내장 에이전트 위임만 허용하고 API·외부 CLI 호출을 금지한다.
- Lead/Worker/QA 역할과 계획 수정 권한을 강제한다.
- 스킬 본문은 500줄 미만으로 유지한다.

확정 frontmatter:

```yaml
---
name: codex-dev-plan-orchestrator
description: Create, upgrade, validate, execute, resume, independently QA, and report the status of codex-dev-plan/v2 implementation plans. Use when a user asks for an execution-ready implement_*.md plan, wants to upgrade a dev-plan-generator v1 document, implement or resume work from a validated plan using native Codex worker delegation, run an independent Sol QA, or inspect plan status without directly calling the OpenAI API or a separate Codex CLI process.
---
```

### `agents/openai.yaml`

권장 UI 메타데이터:

```yaml
interface:
  display_name: "Codex Dev Plan Orchestrator"
  short_description: "Create, execute, resume, and independently QA dev plans"
  default_prompt: "Use $codex-dev-plan-orchestrator to create or run a validated development plan with native worker delegation and independent Sol QA."
```

`SKILL.md`가 변경되면 메타데이터 의미 일치를 다시 검증한다.

### `scripts/new_dev_plan.py`

- 새 v2 계획을 `DRAFT`로 생성한다.
- `plan_id`, Phase/DEV/TEST/QA ID와 최종 `QA-FINAL`을 생성한다.
- 목적·범위·제외 범위·Phase 정보를 CLI 인수 또는 구조화된 입력으로 받는다.
- 플레이스홀더가 남은 계획을 `READY`로 만들지 않는다.
- 동일 초에 파일명이 충돌하면 덮어쓰지 않고 명시적으로 실패한다.

### `scripts/upgrade_dev_plan.py`

- v1 원본을 읽되 수정하지 않는다.
- 새 타임스탬프의 v2 파일을 생성한다.
- 확정할 수 없는 필드를 `TODO`로 남긴다.
- 원본 경로와 해시를 참조 문서 및 메타데이터에 기록한다.
- 생성 후 구조 검증을 실행하며 `TODO`가 있으면 `DRAFT`를 유지한다.
- `TODO`가 없으면 planning evidence와 target READY 검증 후 `READY`로 전환한다.

### `scripts/validate_dev_plan.py`

두 검증 레벨을 제공한다.

| 레벨 | 허용 상태 | 목적 |
|---|---|---|
| `structural` | 모든 허용 계획 상태 | 문서 구조·ID·참조·상태 일관성 검사 |
| `executable` | 기본 `READY`, `IN_PROGRESS`, `QA`; `--target-state`로 목표 상태 검사 | 실행 전 필수 정보·플레이스홀더·게이트 검사 |

성공은 종료 코드 `0`, 검증 실패는 `1`, 사용법 또는 내부 오류는 `2`를 반환한다.
사람이 읽는 텍스트 출력과 선택적 `--format json` 출력을 제공한다.

### `scripts/update_plan_state.py`

Lead Sol만 호출한다.

- `apply-event` 하위 명령으로 허용 이벤트만 적용한다.
- `--expected-document-sha256`과 `document_version` compare-and-swap으로 경쟁
  갱신을 감지한다.
- 대상 파일과 동일 디렉터리에 잠금 파일을 사용한다.
- 잠금 안에서 재읽기 → evidence 검증 → 이벤트의 모든 엔터티와 파생 체크박스 계산
  → 전체 불변식 검증 → 임시 파일 `fsync` → `os.replace` → 디렉터리 `fsync`
  순서로 원자적 교체한다.
- 변경 전 문서를
  `dev-plan/evidence/<plan-id>/state-history/<version>-<timestamp>-<sha256>.md`에
  보존한다.
- `--dry-run`에서 diff를 출력하고 파일을 변경하지 않는다.
- 잠금에는 host·owner PID·생성 시각·예상 문서 digest를 기록한다. 기본 획득 대기는
  30초, stale 기준은 10분이다. 같은 host에서 PID 종료를 확인했거나 사용자가
  승인한 경우에만 stale lock을 회수한다.

### `scripts/package_skill.py`

- 파일 단위 런타임 allowlist만 임시 디렉터리에 복사한다.
- 설치 폴더명을 `codex-dev-plan-orchestrator`로 고정한다.
- 개발 전용 패키징 스크립트·문서·테스트·캐시·evidence를 제외한다.
- 패키징 후 `quick_validate.py`를 실행할 수 있는 경로를 출력한다.

### `references/`

현재 구현 전에는 `docs/02`, `docs/03`, `docs/04`가 규격 정본이다. Phase 1에서
내용을 `references/`로 이전한 뒤에는 `references/`만 규격 정본으로 유지하고,
해당 `docs/` 파일은 요약과 정본 링크만 남긴다. 동일 규격을 두 위치에서 수동
복제하지 않는다.

## 4. 계획 문서 저장 구조

대상 프로젝트 안에서 다음 구조를 사용한다.

```text
dev-plan/
├── implement_YYYYMMDD_HHMMSS.md
└── evidence/
    └── <plan-id>/
        ├── baseline/
        ├── <task-id>/
        │   └── attempt-0001/
        │       ├── contract.yaml
        │       ├── worker-report.yaml
        │       ├── test.log
        │       ├── pre-state.json
        │       ├── post-state.json
        │       └── diff.patch
        ├── <qa-id>/
        │   └── attempt-0001/
        │       ├── qa-contract.yaml
        │       ├── qa-response.txt
        │       ├── qa-report.yaml
        │       ├── pre-state.json
        │       └── post-state.json
        └── state-history/
```

계획 상태는 Markdown이 정본이다. evidence는 상태의 근거이며 계획 상태를 대체하지
않는다.

## 5. 모델 선택 계층

모델 이름을 하드코딩된 가정으로 처리하지 않는다.

1. 런타임에서 위임 도구와 사용 가능한 모델을 확인한다.
2. `ROUTINE` 태스크는 Terra 계열에 배정한다.
3. `COMPLEX` 태스크는 Luna가 실제 제공될 때만 Luna에 배정한다.
4. Luna가 없으면 경로·의존성·완료 기준을 기준으로 태스크를 축소 분할한다.
5. 분할된 각 태스크가 독립적으로 검증 가능할 때만 Terra로 재배정한다.
6. 안전한 분할이 불가능하면 계획을 `BLOCKED`로 전환한다.

계획에는 논리 등급과 실제 식별자를 모두 기록한다.

가용 모델의 정본은 런타임 위임 도구가 노출하는 모델 enum이다. 현재 환경에서는
`gpt-5.6-sol`, `gpt-5.6-terra`만 사용 가능하며 Luna는 미지원으로 처리한다.
Worker와 QA는 `fork_turns: "none"`과 정확한 모델 식별자를 명시해 생성한다.
동시 슬롯이 부족하면 실패로 위장하지 않고 실행 가능한 수만 wave로 시작하고 나머지는
순차 대기한다.

## 6. 격리 실행

- Worker와 QA는 원본 작업공간을 직접 수정하는 방식으로 병렬 실행하지 않는다.
- Git clean 상태는 태스크별 disposable worktree를 사용한다.
- dirty Git 또는 비-Git 상태는 전체 보호 범위가 포함된 disposable snapshot을
  만들고 content manifest로 동일성을 확인한다.
- Worker 결과는 격리 공간의 pre/post manifest로 산출한 patch다. Lead가 허용 경로,
  현재 원본 상태, 충돌을 재검증한 뒤 원본에 통합한다.
- QA는 Worker 결과가 적용된 disposable snapshot에서 테스트하고 구조화된 응답만
  반환한다. Lead가 응답 원문을 변경 없이 저장하고 SHA-256을 기록한다.
- 격리 공간은 성공·실패와 무관하게 감사 자료 저장 후 폐기한다.

## 7. 런타임 의존성

- 구현은 Python 3.11 이상을 기준으로 한다.
- Markdown AST와 안전한 제한 YAML 로더가 필요하므로 `markdown-it-py`와 PyYAML의
  지원 버전을 `pyproject.toml`에 고정하고 런타임 패키지에 의존성 메타데이터를
  포함한다.
- 스크립트는 시작 시 의존성을 preflight하고, 누락 시 자동 네트워크 설치를 시도하지
  않고 설치 방법을 포함한 명시적 오류로 중단한다.
- 외부 명령은 `shell=False`, 구조화된 `argv`, 고정된 프로젝트 상대 `cwd`, 정제된
  환경변수로 실행한다.

## 8. 설치 및 원본 보호

- 기존 `/Users/hwanchoi/.codex/skills/dev-plan-generator`는 읽기 전용 참조다.
- 개발 중 전역 스킬 폴더에 직접 쓰지 않는다.
- 저장소에서 테스트와 패키지 검증을 통과한 뒤 설치한다.
- 설치 전에 기존 동일 이름 폴더가 있으면 자동 덮어쓰지 않고 사용자 승인을 받는다.
- 설치 후에도 Git 저장소가 원본 정본이며 전역 설치본에서 직접 개발하지 않는다.
