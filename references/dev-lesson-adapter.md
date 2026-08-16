# V2 Dev Lesson Adapter

이 문서는 V1 `dev-plan-generator`가 소유한 공통 Dev Lesson 정책·도구를 V2 실행에서 사용하는 얇은 어댑터 규칙이다. V2 패키지는 공통 스크립트를 복제하지 않는다.

## 1. 공통 도구 확인

활성 skill metadata에서 `dev-plan-generator`의 실제 설치 경로를 확인하고 `<DEV_PLAN_SKILL_DIR>/scripts/dev_lesson.py`를 사용한다. 사용자 홈 절대경로를 문서나 계획에 고정하지 않는다. V1 `find` 결과의 `repo_path`만 candidate references에 사용한다.

V1을 V2보다 먼저 설치하고 `check_dev_lesson_tool.py`가 `dev-lesson-tool/v1`, `dev-lesson/v1`, `find|record|validate`, `repo_path|v2_evidence|advisory_only` capability를 확인해야 한다.

도구가 없으면 `LESSON_TOOL_UNAVAILABLE`을 명시적으로 보고한다. Lesson 검색·기록 성공으로 가장하지 않으며, advisory 기능의 누락만으로 V2 ASSESS/PLAN을 자동 차단하지 않는다.

## 2. PLAN 전 검색

1. ASSESS에서 자연스러운 scope unit과 대상 file/tree를 먼저 식별한다.
2. V2 계획 JSON을 만들기 전에 공통 `find`를 실행한다.
3. exact path/tag로 관련된 active Lesson만 candidate의 `references`에 넣는다.
4. 검색 결과마다 `adopted | not-applicable | waived` 판단을 남긴다. adopted는 prevention control과 적용 task/test 위치, not-applicable은 scope 이유, waived는 승인자·만료·보상 control이 필수다.
5. 검색 0건은 정상 결과이며 억지 Lesson 참조를 만들지 않는다.

과거 Lesson은 계획 생성 전에만 references에 포함한다. 생성된 `parallel_*.json`과 렌더된 `parallel_*.md`는 Lesson 때문에 다시 수정하지 않는다.

## 3. 실행 중 후보

- Worker는 `docs/dev-lessons/`를 수정하지 않는다. validator는 `docs/`, `docs/dev-lessons/` 또는 그 하위 경로를 모든 plan unit의 write scope로 선언하지 못하게 차단한다.
- Worker는 문제 발생 시 다음 사실만 Lead에게 반환한다: `occurrence_id`, 시각, 증상, 영향, 재현/증거, 임시조치, scope unit, commit/test/scope 증거.
- Worker는 root cause나 Lesson 승격을 확정하지 않는다.
- 같은 문제를 여러 Worker가 보고해도 Lead가 통합 단계에서 한 후보로 정리한다.

## 4. 통합·QA 후 기록

1. 모든 lane의 scope/test 결과와 통합 QA를 먼저 완료한다.
2. Lead가 각 후보를 `plan-only | existing-reference | new-lesson`으로 한 번만 분류한다.
3. exact `dedupe_key`가 있으면 새 파일을 만들지 않고 기존 ID를 참조한다.
4. 신규 교훈은 공통 `record`로 별도 `docs/dev-lessons/DL-*.md`에 생성한다.
5. 선택적 `v2_evidence`에는 `plan_id`, `scope_unit`, `baseline`, `commit`, `scope_result`, `test_ref`, `qa`만 넣는다.
6. 모든 분류와 과거 Lesson disposition을 `execution_outcomes.py create --lesson-tool-script <V1_SCRIPT>`로 인접한 `parallel_*.outcomes.json`에 기록한다.

신규 Lesson은 V2 plan/ledger가 아니라 별도 추적 문서다. outcomes sidecar는 plan·ledger SHA와 occurrence 사실·분류·Lesson ID, V1 검증을 통과한 Lesson의 repo-relative path·SHA를 보존하지만 두 정본을 수정하지 않는다. `new-lesson`과 `existing-reference`는 실제 파일과 V1 `validate` 성공 없이는 기록할 수 없다. 공통 도구가 없으면 Lesson ID를 주장하지 않고 `record-pending`으로 보존한다. MVP에서는 plan 역링크, ledger `lesson_ids`, occurrence append를 추가하지 않는다.

## 5. Outcomes 입력

`execution_outcomes.py create` 입력은 다음 세 필드만 가진다.

```json
{
  "lesson_tool": {
    "status": "AVAILABLE",
    "detail": "dev-lesson-tool/v1 compatible"
  },
  "prior_lessons": [
    {
      "lesson_id": "DL-20260815T120000Z-a1b2c3d4",
      "disposition": "adopted",
      "reason": "WS-01 scope와 동일한 failure mode",
      "control": "tenant 격리 회귀 테스트",
      "task_refs": ["WS-01: tenant-aware key"],
      "test_refs": ["pytest tests/api"],
      "waiver": null
    }
  ],
  "occurrences": [
    {
      "occurrence_id": "OCC-001",
      "source_units": ["WS-01"],
      "summary": "redacted symptom",
      "impact": "one lane rework",
      "evidence": "tracked test and scope report",
      "temporary_action": "returned to WS-01",
      "disposition": "new-lesson",
      "reason": "reusable prevention control",
      "lesson_id": "DL-20260815T120001Z-b1b2c3d4",
      "durable_refs": ["tests/api/test_scope.py", "commit:<sha>"]
    }
  ]
}
```

`adopted`는 control·task_refs·test_refs가 필수다. `not-applicable`은 scope 이유만, `waived`는 reason·approver·expiry·compensating_control을 기록한다. `record-pending`은 `LESSON_TOOL_UNAVAILABLE`일 때만 허용하고 Lesson ID를 주장하지 않는다.

## 6. 불변성과 적용 강도

- `parallel_*.json`은 기계 정본이고 Markdown은 바이트 단위 재렌더 대상이다.
- ledger는 plan SHA를 고정한다. plan을 수정해 Markdown drift 또는 `RESUME_BLOCKED`를 만들지 않는다.
- outcomes는 plan과 정확히 일치하는 모든 unit의 완전한 scope/test/QA/reviewer/commit 증거를 확인하고 commit diff로 scope status/files/fingerprint를 재계산한 뒤 한 번만 생성하며 기존 파일을 덮어쓰지 않는다.
- 과거 Lesson disposition은 해당 ID가 plan references에 있고 V1 검증을 통과할 때만 허용한다. `verified_lessons` hash가 바뀌면 outcomes 검증은 실패한다.
- `validate`에도 같은 `--lesson-tool-script`를 전달해 Lesson과 sidecar hash가 함께 바뀐 경우에도 실제 V1 validation을 다시 수행한다.
- Lesson은 advisory다. fuzzy/tag-only match, stale review warning, 도구 부재는 자동 hard gate가 아니다.
- raw log, secret, token, cookie, 고객 식별정보, 내부 제한 URL을 후보나 Lesson에 넣지 않는다.
- outcomes 자동 민감정보 검사는 보조 수단이다. Lead의 redaction·privacy 검토를 대체하지 않는다.
