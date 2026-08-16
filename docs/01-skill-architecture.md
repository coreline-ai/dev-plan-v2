# 아키텍처

| 계층 | 책임 |
|---|---|
| `SKILL.md` | V1/V2 선택, ASSESS, Git 실행·QA 운영 계약 |
| `parallel_plan_lib.py` | 공통 JSON 모델, 경로·의존성·Wave, Markdown renderer |
| `assess_parallelism.py` | 직렬·COMMON 선행·병렬 안전성 판정 |
| `new_parallel_dev_plan.py` | JSON 정본과 Markdown 표현을 한 쌍으로 생성 |
| `validate_parallel_dev_plan.py` | JSON 구조와 Markdown 재렌더링 일치 검증 |
| `preflight_parallel_exec.py` | clean baseline과 worktree 사용 가능 여부 검사 |
| `check_parallel_scope.py` | 한 worktree의 실제 Git 변경 전체를 lane 경계와 대조 |
| `execution_ledger.py` | commit·scope·test·QA 실행 사실과 재개 상태 기록 |
| `execution_outcomes.py` | plan/ledger를 수정하지 않는 post-QA Lesson disposition sidecar |
| `check_dev_lesson_tool.py` | 별도 설치된 V1 공통 도구의 capability 호환 확인 |
| V1 Dev Lesson 공통 도구 | 대상 프로젝트의 Lesson 생성·검증·검색 정본 |
| `references/dev-lesson-adapter.md` | V2의 PLAN 전 검색, Worker 후보 반환, Lead-only 기록 규칙 |
| `references/` | 입력 형식과 실행 상세 정본 |

Python 도구는 코드의 의미를 임의로 추론하거나 merge·push하지 않는다. Lead가 코드·문서에서 의미적 근거를 수집하고 도구는 구조와 실제 Git 증거를 검증한다.

ASSESS는 별도 점수나 자연어 parser 없이 세 gate만 사용한다.

1. 제거해도 완료 기준을 만족하는 Workstream은 삭제한다.
2. 공유 계약과 선행 설계가 남은 작업은 직렬 또는 원래 필요한 COMMON으로 보낸다.
3. 실제 병렬 이점 근거가 없거나 residual coordination risk가 남으면 직렬로 보낸다.

직렬 판정은 V2 산출물을 만들지 않고 종료하며, 안전 판정만 기존 plan v3·worktree·ledger·outcomes 경로로 진입한다. 사용자 요청 수와 Workstream 수는 비교하지 않는다.

Dev Lesson 코어는 V2에 복제하지 않는다. V2는 기존 plan/ledger schema를 유지하고 V1 공통 도구를 사용하는 실행 절차만 제공한다.
