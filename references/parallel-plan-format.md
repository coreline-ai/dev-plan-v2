# 병렬 계획 형식

## Candidate spec

`assess_parallelism.py`와 `new_parallel_dev_plan.py --spec`은 `parallel-dev-candidate/v1` JSON을 입력받는다. 의미적 결합 정보는 Lead가 코드·문서를 읽고 작성하며 스크립트가 임의로 추론하지 않는다.

candidate를 확정하기 전에 자연스러운 file/tree scope로 공통 Dev Lesson 검색을 수행한다. 관련 과거 Lesson은 기존 `references` 문자열에 repo-relative 경로로 추가한다. 검색 0건은 정상이며 Lesson 전용 schema 필드는 추가하지 않는다.

```json
{
  "schema": "parallel-dev-candidate/v1",
  "purpose": "API와 UI의 오류 처리를 구현한다",
  "scope": ["오류 응답과 표시"],
  "exclude": ["인증 흐름 변경"],
  "references": ["docs/error-contract.md"],
  "semantic_blockers": [],
  "shared_contracts": ["src/contracts/error.py"],
  "coordination_risks": [],
  "assessment_reasons": [
    "두 lane은 최소 구현에 모두 필요하고 COMMON 이후 독립 테스트가 가능하며 동시 실행 이점이 명확하다"
  ],
  "common": {
    "id": "COMMON",
    "goal": "오류 계약을 확정한다",
    "write_paths": ["src/contracts/error.py"],
    "read_context": [],
    "depends_on": [],
    "tests": ["python3.11 -m pytest tests/contracts"],
    "required_capabilities": ["python"],
    "risk": "high"
  },
  "workstreams": [
    {
      "id": "WS-01",
      "goal": "API 오류 응답을 구현한다",
      "write_paths": ["src/api/", "tests/api/"],
      "read_context": ["src/contracts/error.py"],
      "depends_on": ["COMMON"],
      "tests": ["python3.11 -m pytest tests/api"],
      "required_capabilities": ["python", "api"],
      "risk": "medium"
    },
    {
      "id": "WS-02",
      "goal": "UI 오류 표시를 구현한다",
      "write_paths": ["src/web/", "tests/web/"],
      "read_context": ["src/contracts/error.py"],
      "depends_on": ["COMMON"],
      "tests": ["python3.11 -m pytest tests/web"],
      "required_capabilities": ["web"],
      "risk": "medium"
    }
  ],
  "integration": {
    "id": "INTEGRATION",
    "goal": "전체 회귀를 검증한다",
    "write_paths": [],
    "read_context": [],
    "depends_on": ["WS-01", "WS-02"],
    "tests": ["python3.11 -m pytest"],
    "required_capabilities": [],
    "risk": "high"
  },
  "phases": ["공유 계약 확정", "병렬 구현", "통합 검증"],
  "compliance": {"require_actual_model": false}
}
```

## 판정 규칙

- 먼저 사용자 완료 기준을 만족하는 최소 직렬 구현 경로를 확인한다.
- 각 Workstream을 제거해도 완료 기준을 만족하면 candidate에서 제거한다.
- 사용자 요청 수와 Workstream 수는 비교하지 않는다.
- 테스트·문서·QA는 해당 구현의 완료 조건이며, 병렬화를 위한 리팩터링·추상화·중간 API는 별도 lane이 아니다.
- `assessment_reasons`에는 필요성·독립성·실제 병렬 이점을 확인한 짧은 근거가 최소 하나 있어야 한다. 스크립트는 자연어 의미를 추론하지 않는다.
- `coordination_risks`에는 COMMON 이후에도 남는 위험만 기록한다. 항목이 남아 있으면 통합 재작업 가능성이 있으므로 직렬이다.
- `SERIAL_RECOMMENDED`: 근거 없음, residual coordination risk, Workstream 둘 미만, 독립 테스트 누락, write 경로 중복 또는 semantic blocker 존재
- `COMMON_FIRST`: 공유 계약이 있고 독립 구현 전 COMMON 확정이 가능
- `PARALLEL_SAFE`: 둘 이상의 자연스러운 책임 단위, 비중복 write 경로, 독립 테스트, 의미적 blocker 없음
- `BLOCKED`: 입력·의존성·통합 검증 근거가 누락되거나 모순됨

`COMMON_FIRST`인데 COMMON unit이 없으면 계획 파일을 만들지 않는다.

`SERIAL_RECOMMENDED`에서는 V2 plan/worktree/ledger를 만들지 않는다. `COMMON_FIRST`와 `PARALLEL_SAFE`에서만 JSON/Markdown 한 쌍을 한 번 생성한다.

## 경로 규칙

- `write_paths`는 저장소 기준 상대 파일 또는 `/`로 끝나는 디렉터리 prefix다.
- 절대 경로, glob, `..`, 역슬래시, 비정규 `./` 경로는 금지한다.
- 계획상 write 경로는 한 scope unit만 소유한다.
- `read_context`는 읽기 전용이며 여러 unit과 겹칠 수 있다.
- integration 전체 테스트는 필수지만 integration write 경로는 빈 목록일 수 있다.
- `docs/dev-lessons/`는 post-QA Lead 전용 예약 경로다. 상위 `docs/`를 포함해 어떤 plan scope unit도 이를 소유할 수 없다.

## 생성 결과

```text
dev-plan/parallel/
├── parallel_YYYYMMDD_HHMMSS.json
├── parallel_YYYYMMDD_HHMMSS.md
├── parallel_YYYYMMDD_HHMMSS.execution.json
└── parallel_YYYYMMDD_HHMMSS.outcomes.json
```

JSON이 기계 판정 정본이며 Markdown은 같은 JSON을 렌더링한 표현이다. validator는 JSON 구조, Wave, 경로 소유권과 Markdown 재렌더링 일치를 함께 검사한다.

`previous_plan`은 참조 문서 첫 항목에만 넣고 기존 V1/V2 파일을 수정하지 않는다.

Lesson reference도 계획 생성 전에만 넣는다. 실행 중 발생한 신규 Lesson을 역링크하기 위해 생성된 JSON이나 Markdown을 수정하면 안 된다.

`outcomes.json`은 실행 완료 후 생성되는 별도 사실 기록이다. plan·ledger SHA, 완전한 실행 증거 검증, 과거 Lesson disposition, occurrence 사실과 최종 분류, 검증된 Lesson 경로·SHA를 보존하며 plan schema를 변경하지 않는다.
