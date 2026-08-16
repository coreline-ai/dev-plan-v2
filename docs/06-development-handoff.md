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

패키징은 빈 출력 디렉터리에서 수행한다.

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```
