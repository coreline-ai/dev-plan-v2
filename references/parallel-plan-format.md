# 병렬 계획 형식

## Candidate spec

`assess_parallelism.py`와 `new_parallel_dev_plan.py --spec`은 `parallel-dev-candidate/v1` JSON을 입력받는다. 의미적 결합 정보는 Lead가 코드·문서를 읽고 작성하며 스크립트가 임의로 추론하지 않는다.

```json
{
  "schema": "parallel-dev-candidate/v1",
  "purpose": "API와 UI의 오류 처리를 구현한다",
  "scope": ["오류 응답과 표시"],
  "exclude": ["인증 흐름 변경"],
  "references": ["docs/error-contract.md"],
  "semantic_blockers": [],
  "shared_contracts": ["src/contracts/error.py"],
  "coordination_risks": ["오류 코드 불일치"],
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

- `SERIAL_RECOMMENDED`: Workstream이 둘 미만, 독립 테스트 누락, write 경로 중복 또는 semantic blocker 존재
- `COMMON_FIRST`: 공유 계약이 있고 독립 구현 전 COMMON 확정이 가능
- `PARALLEL_SAFE`: 둘 이상의 자연스러운 책임 단위, 비중복 write 경로, 독립 테스트, 의미적 blocker 없음
- `BLOCKED`: 입력·의존성·통합 검증 근거가 누락되거나 모순됨

`COMMON_FIRST`인데 COMMON unit이 없으면 계획 파일을 만들지 않는다.

## 경로 규칙

- `write_paths`는 저장소 기준 상대 파일 또는 `/`로 끝나는 디렉터리 prefix다.
- 절대 경로, glob, `..`, 역슬래시, 비정규 `./` 경로는 금지한다.
- 계획상 write 경로는 한 scope unit만 소유한다.
- `read_context`는 읽기 전용이며 여러 unit과 겹칠 수 있다.
- integration 전체 테스트는 필수지만 integration write 경로는 빈 목록일 수 있다.

## 생성 결과

```text
dev-plan/parallel/
├── parallel_YYYYMMDD_HHMMSS.json
└── parallel_YYYYMMDD_HHMMSS.md
```

JSON이 기계 판정 정본이며 Markdown은 같은 JSON을 렌더링한 표현이다. validator는 JSON 구조, Wave, 경로 소유권과 Markdown 재렌더링 일치를 함께 검사한다.

`previous_plan`은 참조 문서 첫 항목에만 넣고 기존 V1/V2 파일을 수정하지 않는다.
