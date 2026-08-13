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
| `references/` | 입력 형식과 실행 상세 정본 |

Python 도구는 코드의 의미를 임의로 추론하거나 merge·push하지 않는다. Lead가 코드·문서에서 의미적 근거를 수집하고 도구는 구조와 실제 Git 증거를 검증한다.
