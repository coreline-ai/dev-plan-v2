# 실행·재개·QA 흐름

## 실행 전: fail-closed preflight

1. 계획을 구조 검사하고, 네이티브 위임 런타임의 실제 모델 목록을 조회한다.
2. 현재 Lead가 Sol인지 확인한다. 아니면 `fork_turns: none`의 새 Sol Lead를 만들고,
   이것도 불가하면 `BLOCKED`다.
3. 목록에서 정확한 Sol/Terra/Luna ID를 선택해 계획의 `확인된 런타임 모델`과
   `requested model`에 기록한다.
4. ROUTINE은 Terra, COMPLEX는 Luna, QA는 Worker와 분리된 새 Sol로 명시 위임한다.
   Luna 미제공 시 `BLOCKED` 또는 Terra-safe 재분해만 허용한다.
5. `--ready`를 통과한다. 기본 모델 상속·별칭 추정·Terra 대체는 허용하지 않는다.

## 실행

각 위임은 정확한 `model`과 `fork_turns: "none"`을 명시한다. Worker에는 한 책임 단위의
목표, 허용 변경 범위, 완료 기준, 테스트 명령, 보고 형식만 전달한다. 생성 후 host가 반환한
모델 ID를 `actual model`에 기록한다. 값이 없거나 requested와 다르면 작업 결과를 수용하지
말고 `BLOCKED`로 남긴다.

Lead는 Worker의 diff와 실제 테스트를 재확인한 뒤에만 체크를 갱신한다. Worker 보고에는
변경 파일, 실제 실행 명령/결과, requested/actual model, 미해결 위험을 넣는다.

## 재개와 QA

RESUME은 첫 미완료 Phase부터 시작한다. 마지막 diff·테스트·모델 기록이 불명확하면
`BLOCKED`로 남긴다. QA는 Worker와 분리된 새 Sol 컨텍스트에서 완료 조건, diff, 실제
테스트만 검토해 `PASS`, `FIX`, `BLOCKED`를 반환한다. QA 결과와 host actual model을 기록한다.

`PASS`만 완료다. 최종적으로 `validate_dev_plan.py <plan> --complete`를 실행해 exact model
기록, 테스트, 모든 완료 체크, QA PASS를 확인한다.
