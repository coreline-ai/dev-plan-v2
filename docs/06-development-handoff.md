# 개발 핸드오프

최종 갱신: `2026-07-25 KST`

## 1. 현재 상태

- 원본 저장소: `/Volumes/Eprojects/project_202607/dev-plan-v2`
- Git 기본 브랜치: `main`
- 저장소 역할: `codex-dev-plan-orchestrator` 원본 소스
- 기존 `dev-plan-generator` 분석 완료
- v2 스키마·상태 전이·실행·QA 계약 보완 완료
- 실제 `SKILL.md`, scripts, references, tests 구현은 아직 시작하지 않음

현재 상태는 **설계 완료, 구현 착수 가능**이다. 구현 완료 또는 설치 가능 상태를
의미하지 않는다.

## 2. 확정된 결정

1. 저장소 루트를 개발 원본으로 사용한다.
2. 기본 브랜치는 `main`이다.
3. 설치 시 폴더명은 `codex-dev-plan-orchestrator`로 고정한다.
4. 기존 `dev-plan-generator`는 읽기 전용 참조로 유지한다.
5. v2 Markdown 계획 문서가 실행 상태의 정본이다.
6. evidence는 계획 상태의 근거이며 정본을 대체하지 않는다.
7. 구조 검증과 실행 가능성 검증을 분리한다.
8. 상태 변경은 이벤트·document digest CAS·잠금·검증·원자적 교체·이력 보존을
   사용한다.
9. 현재 지원 Worker는 Terra이며 Luna는 런타임 제공 시에만 사용한다.
10. QA는 새 Sol, 최소 컨텍스트, 실제 diff 중심으로 수행한다.
11. Worker와 QA는 disposable worktree/snapshot에서 실행한다.
12. QA 전후 전체 보호 manifest로 무수정 여부를 확인한다.
13. evidence는 attempt별 append-only 경로와 SHA-256을 사용한다.
14. API와 외부 Codex CLI를 사용하지 않는다.

## 3. 구현자가 읽을 순서

1. `docs/00-project-overview.md`
2. `docs/01-skill-architecture.md`
3. `docs/02-plan-schema-v2.md`
4. `docs/03-execution-workflow.md`
5. `docs/04-agent-roles-and-contracts.md`
6. `docs/05-validation-and-test-plan.md`
7. `docs/07-expert-revalidation.md`

기존 동작 참고:

- `/Users/hwanchoi/.codex/skills/dev-plan-generator/SKILL.md`
- `/Users/hwanchoi/.codex/skills/dev-plan-generator/scripts/new_dev_plan.py`

기존 파일을 복사해 수정할 수는 있지만 원본 위치에는 쓰지 않는다.

## 4. 구현 권장 순서

### Phase 1. 저장소 스캐폴딩

- 저장소 루트가 이미 존재하므로 skill-creator의 `init_skill.py`를 임시 staging
  디렉터리에서 실행하고 생성된 `SKILL.md`, `agents/`, `scripts/`, `references/`
  구조를 저장소 루트로 옮긴다.
- 저장소 루트에 `tests/`를 추가한다.
- `pyproject.toml`, `.gitignore` 구성
- skill-creator의 `init_skill.py` 산출물과 형식 대조
- `agents/openai.yaml` 생성
- `docs/02~04`의 정본 내용을 `references/`로 이전하고 docs에는 정본 링크만 유지

완료 기준:

- 기본 `quick_validate.py` PASS
- 테스트 러너가 빈 스모크 테스트를 실행
- 원본 기존 스킬 SHA-256 baseline 저장

### Phase 2. v2 파서와 생성기

- 공통 parser/model 모듈 구현
- `new_dev_plan.py` 구현
- canonical Markdown/YAML serializer 구현
- ID·시간·경로 유효성 검사

완료 기준:

- 생성기 및 round-trip 단위 테스트 PASS
- 예시 계획 structural 검증 PASS

### Phase 3. 검증기와 상태 갱신기

- structural/executable 검증
- 상태 전이 매트릭스
- 이벤트 기반 다중 엔터티 전이와 document digest/version CAS
- 체크박스 파생 규칙
- 잠금, dry-run, 원자적 교체, 이력 보존

완료 기준:

- 문서 05의 검증기·갱신기 테스트 PASS
- 실패 주입 시 원본 파일 보존

### Phase 4. v1 업그레이드와 패키징

- 다양한 v1 fixture 파서
- 원본 해시·참조 기록
- `package_skill.py` allowlist

완료 기준:

- v1 원본 무변경
- 불완전 업그레이드는 `DRAFT`
- 패키지에 개발 파일 미포함

### Phase 5. SKILL 및 실행 계약

- 7개 모드 판별과 부작용 경계
- 모델 가용성 확인 및 라우팅
- Worker/QA 계약과 evidence 규칙
- disposable worktree/snapshot, attempt lease, wave scheduling
- BLOCKED·재작업·재개 흐름

완료 기준:

- `SKILL.md` 500줄 미만
- reference 링크와 UI 메타데이터 일치
- API·외부 CLI 금지 정적 검사 PASS

### Phase 6. 통합·전방 검증

- 기능 시나리오 A~S
- 최소 컨텍스트 신규 에이전트 전방 테스트
- Worker/QA 생성에 `fork_turns: "none"`과 exact model ID 확인
- QA 무수정과 독립성 검사
- 패키지 설치 전 최종 감사

완료 기준:

- 출시 게이트 전체 충족
- `docs/07-expert-revalidation.md`에 최종 결과 추가

## 5. 구현 세부 지침

- 공통 parser를 각 스크립트에서 중복 구현하지 않는다.
- Markdown을 정규식만으로 부분 수정하지 않는다.
- YAML 로딩은 안전 로더를 사용하고 임의 객체 생성을 허용하지 않는다.
- YAML 의존성 버전을 고정하고 누락 시 자동 설치하지 않는다.
- serializer는 동일 입력에 안정된 출력을 생성해야 한다.
- 사용자 명령을 셸 문자열로 재조합하지 말고 인수 배열로 실행한다.
- 검증 명령에는 timeout을 적용하고 로그 크기 상한을 둔다.
- 절대 경로를 evidence에 고정하지 말고 프로젝트 기준 상대 경로를 저장한다.
- 테스트와 패키징은 임시 디렉터리에서 원본 프로젝트를 오염시키지 않게 수행한다.
- 전역 스킬 설치는 모든 검증 완료 후 별도 사용자 요청 또는 승인을 받아 수행한다.

## 6. 완료 정의

다음 조건을 모두 충족하면 신규 스킬 개발 완료다.

- 원본 저장소 구조 완성
- PLAN/UPGRADE/VALIDATE/EXECUTE/RESUME/QA/STATUS 지원
- v2 생성·검증·상태 갱신 성공
- v1 업그레이드와 원본 보존 성공
- Terra 라우팅 성공
- Luna 제공 또는 부재 정책의 정확한 동작
- Independent QA의 독립성과 무수정 검증 성공
- QA 실패 후 제한된 재작업 성공
- 중단 후 안전한 재개 성공
- 최종 통합 QA와 Lead 승인 성공
- 패키징·quick validation 성공
- API 및 외부 Codex CLI 미사용 확인
- 기존 `dev-plan-generator` 무변경 확인

## 7. 지금 바로 시작할 첫 작업

첫 구현 작업은 스캐폴딩과 공통 v2 parser/model이다. 실행 오케스트레이션보다
결정적인 문서 생성·검증·상태 변경을 먼저 완성해야 이후 에이전트 흐름을 신뢰할 수
있다.
