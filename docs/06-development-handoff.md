# 개발 핸드오프

- 일반 계획과 결합 작업은 V1을 사용한다.
- 명시적 병렬 요청도 ASSESS 결과가 안전할 때만 V2 계획을 만든다.
- JSON이 정본이고 Markdown은 표현 문서다.
- 사용자 변경은 자동 stash·commit하지 않는다.
- COMMON 이후 lane baseline, per-worktree scope, 실제 테스트, 위험도별 QA가 모두 필요하다.
- 모델 metadata는 compliance가 요구할 때만 완료 gate다.
- 과거 Dev Lesson은 PLAN 전에 references에 넣고, 실행 후보는 Worker가 증거만 반환한다.
- 통합·QA 후 Lead만 별도 Lesson을 기록하며 plan JSON/Markdown과 ledger는 수정하지 않는다.
- 완료 분류는 인접한 immutable outcomes sidecar에 남기고 도구 부재는 `record-pending`으로 보존한다.
- V1을 먼저 설치하고 capability READY를 확인한 뒤 V2를 설치한다. `AVAILABLE` outcomes create/validate에는 같은 V1 `dev_lesson.py`를 전달한다.
- high/critical Lesson은 trusted external human-approval provider가 없는 advisory MVP에서 생성하지 않는다.

## 설치·trigger 핸드오프

- V1 source: `https://github.com/coreline-ai/dev-plan-skill.git`
- V2 source: `https://github.com/coreline-ai/dev-plan-v2.git`
- canonical V1: `${CODEX_HOME:-$HOME/.codex}/skills/dev-plan-generator`
- canonical V2: `${CODEX_HOME:-$HOME/.codex}/skills/parallel-dev-plan-orchestrator`
- 일반 `개발 계획`·`구현 계획`은 V1, 명시적인 `병렬 개발 계획`·`병렬화 가능한지 판단`은 V2 ASSESS로 진입한다.
- V2는 V1을 내장하거나 설치하지 않는다. V1이 없으면 일반 계획과 직렬 fallback 계획을 제공한다고 가장하지 않는다.
- 설치 전 두 source 전체 테스트와 package validation을 통과시키고, 빈 임시 `CODEX_HOME/skills`에서 V1→V2 순서로 검증한다.
- 실제 설치 변경 전 각 설치 경로, `SKILL.md` hash, 백업 목적지를 manifest로 남기고 사용자 승인을 받는다.
- `check_dev_lesson_tool.py --check-install-layout --format json`이 `PLAN_SKILL_INSTALL_READY`인지 확인한다.
- `DUPLICATE_SKILL_NAME`은 경로와 hash만 보고한다. 검사기가 rename·삭제·덮어쓰기를 수행하면 안 된다.
- 설치 후 새 Codex 작업에서 일반 요청과 명시적 병렬 요청을 각각 forward-eval한다. 기존 대화의 skill 선택 결과를 재사용하지 않는다.
- rollback은 승인 전에 만든 백업을 canonical 경로로 복원한 뒤 capability/layout 검사를 다시 실행한다.

패키징은 빈 출력 디렉터리에서 수행한다.

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```
