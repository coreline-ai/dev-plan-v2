# 실행·재개·QA 흐름

## 실행 전

1. 계획을 `--ready`로 검사한다.
2. 실제 런타임 모델을 확인한다.
3. Lead는 Sol/high, ROUTINE Worker는 Terra/medium, COMPLEX Worker는 Luna/high,
   QA는 새 Sol/high로 명시 배정한다.
4. 요구 모델이 없으면 모델을 추정·대체하지 않고 `BLOCKED`로 기록하거나 계획을
   Terra-safe 책임 단위로 재분해한다.

## 실행

Worker는 `fork_turns: "none"` 수준의 최소 컨텍스트에서 한 책임 단위만 수행한다.
목표, 허용 변경 범위, 완료 조건, 테스트 명령, 보고 형식을 제공한다. Worker 보고에는
변경 파일, 실제 테스트 결과, requested/actual model, reasoning effort, 위험을 넣는다.
Lead는 diff와 테스트를 재확인한 뒤에만 체크를 갱신한다.

## 재개와 QA

RESUME은 첫 미완료 Phase부터 시작한다. 마지막 diff·테스트·모델 기록이 불명확하면
`BLOCKED`로 남기고 확인 사항을 적는다. QA는 Worker와 다른 새 Sol 컨텍스트에서
실제 diff와 테스트만 검토해 `PASS`, `FIX`, `BLOCKED`를 반환한다. `FIX`와 `BLOCKED`는
완료가 아니다.
