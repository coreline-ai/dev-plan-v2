# 병렬 실행·재개·QA 흐름

## EXECUTE 전 gate

1. Lead는 V2 master 구조를 검사한다.
2. Git 저장소, clean baseline, 사용자 변경 보존, Worker별 worktree 생성을 확인한다. 실패하면 `BLOCKED` 또는 V1/직렬 작업이다.
3. native runtime에서 실제 지원 모델을 확인한다. Lead=Sol, ROUTINE=Terra, COMPLEX=Luna, QA=새 Sol이 정확한 override로 가능한지 확인한다.
4. Luna가 없으면 COMPLEX를 Terra로 숨겨 대체하지 않는다. 안전한 Terra 단위로 재분해하거나 `BLOCKED`다.

## Wave 실행

1. `COMMON`이 있으면 Wave 0에서 직렬 실행한다.
2. 각 Wave마다 Lead는 baseline 기반 worktree 하나와 scope unit 하나를 Worker에게 준다.
3. Worker는 목표·허용/제외 경로·테스트·완료 조건만 받은 `fork_turns: "none"` 컨텍스트에서 작업한다.
4. Lead는 해당 worktree의 `git diff --name-only <baseline>`만 scope checker에 전달한다.

```text
python3.11 <SKILL_DIR>/scripts/check_parallel_scope.py \
  <master-plan> --scope-unit WS-01 --changed-file src/api/error.py
```

`SCOPE_OK`만 통합할 수 있다. `SCOPE_VIOLATION`은 다른 lane·무소유·제외 경로 변경이다. `SCOPE_AMBIGUOUS`는 경로 소유권 또는 입력이 불명확한 경우다. 이 도구는 aggregate diff 입력을 지원하지 않는다.

`INTEGRATION`은 마지막 Wave에서 선언된 통합 경로만 수정한다. lane 코드 결함은 `REWORK-WS-01`처럼 해당 lane의 직렬 unit으로 재배정하고 그 lane의 허용 경로와 같은 방법으로 다시 검사한다.

## 실행 기록과 RESUME

첫 EXECUTE 때 Lead가 master 계획 끝에 선택 `## 실행 기록`을 만든다. 기록 값은 실제 사실만 쓴다.

```md
## 실행 기록
- 시작 시각: ...
- baseline: ...
- scope unit: WS-01
- requested model: <runtime 요청값>
- host actual model: <host 반환값 또는 미노출>
- scope 결과: SCOPE_OK
- 테스트: <실제 명령과 결과>
- QA: PASS | FIX | BLOCKED
```

host actual model이 미노출되거나 요청값과 다르면 exact 모델 검증은 `BLOCKED`다. RESUME은 기록이 없으면 첫 미완료 Phase부터, 기록이 있으면 기록·Git diff·마지막 테스트를 대조해 시작한다. 불일치는 완료로 추정하지 않고 `BLOCKED`다.

## 독립 QA

새 Sol QA에 목적·완료 조건·scope 경계·실제 per-unit/final diff·테스트만 전달한다. QA 결과는 `PASS`, `FIX`, `BLOCKED` 중 하나다. `PASS`만 완료로 취급한다.
