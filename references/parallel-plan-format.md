# 병렬 master 계획 형식

## 생성 입력

`new_parallel_dev_plan.py`는 `--workstream`을 두 번 이상, `--integration`을 한 번 받는다. `--common`은 선택이다. 각 값은 JSON object다.

```json
{
  "id": "WS-01",
  "goal": "API 오류 처리를 구현한다",
  "allow": ["src/api/", "tests/api/"],
  "exclude": ["src/web/"],
  "tests": ["python3.11 -m pytest tests/api"],
  "depends_on": []
}
```

- Workstream ID는 `WS-01` 형식이다.
- `COMMON`과 `INTEGRATION`의 ID는 자동으로 고정된다.
- `allow`는 하나 이상의 저장소 기준 상대 파일 또는 `/`로 끝나는 디렉터리 prefix다.
- glob, 절대 경로, 상위 경로, 다른 unit과 겹치는 허용 경로는 허용하지 않는다.
- 각 Workstream은 테스트를 하나 이상 가져야 한다.
- `depends_on`은 앞선 `COMMON` 또는 다른 Workstream만 참조한다. `INTEGRATION`은 마지막 Wave에 자동 배정된다.

## 문서 구조

```md
# parallel_YYYYMMDD_HHMMSS.md

작성 일시: `...`

## 개발 목적
## 개발 범위
## 제외 범위
## 참조 문서
## 공통 진행 규칙
## Workstream 맵
| ID | 목표 | 허용 경로 | 제외 경로 | 선행 조건 | 테스트 |

## 직렬 scope unit
| ID | 목표 | 허용 경로 | 제외 경로 | 선행 조건 | 테스트 |

## 병렬 실행 Wave
- Wave 0: COMMON
- Wave 1: WS-01, WS-02
- Wave 2: INTEGRATION

## Phase 상태 요약
## QA 관점
## Phase 1. ...
### 목표
### 구현 태스크
### 자체 테스트
### 이슈 및 수정
### 완료 조건
```

`COMMON`이 없으면 Wave 0도 없다. 모든 계획상 scope unit은 정확히 하나의 Wave에 있어야 한다. `REWORK-WS-*`는 실행 중 생성하는 재작업 unit이므로 사전 Wave 표에 넣지 않는다.

## 이력 연결

`--previous-plan <path>`는 `참조 문서`의 첫 목록에 `이전 개발 계획: <path>`를 넣는다. 이전 V1 `implement_*.md`와 V2 `parallel_*.md`는 읽기 참조일 뿐 수정·이동·삭제하지 않는다.
