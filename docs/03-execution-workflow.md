# 실행 흐름

상세 흐름은 [실행 흐름](../references/execution-workflow.md)을 따른다.

실행 전 Lead는 실제 Sol 모델을 확인한다. ROUTINE 작업은 Terra, COMPLEX 작업은 실제
Luna가 있을 때만 배정한다. QA는 Worker와 다른 새 Sol 컨텍스트다. 모든 실행 보고에는
requested/actual model과 reasoning effort, 변경 파일, 실제 테스트 결과를 남긴다.
