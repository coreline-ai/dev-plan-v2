# 아키텍처

| 계층 | 책임 |
|---|---|
| `SKILL.md` | V1/V2 선택, scope gate, native 실행·QA 운영 계약 |
| `new_parallel_dev_plan.py` | V2 master 계획을 `dev-plan/parallel/`에만 생성 |
| `validate_parallel_dev_plan.py` | Markdown 구조·경로 소유권·Wave 정합성 검사 |
| `check_parallel_scope.py` | 한 scope unit의 격리 changed-file 목록 검사 |
| `references/` | 계획 형식과 실행·재개·QA 상세 정본 |

자동 스크립트는 native 모델 가용성·host actual ID·QA 성공을 판정하지 않는다. 그 책임은 EXECUTE/RESUME의 Sol Lead와 독립 Sol QA에 있다.
