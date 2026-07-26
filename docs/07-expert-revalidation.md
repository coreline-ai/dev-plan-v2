# 전문가 재검증 기준

## 유지한 원칙

- V1 수준의 목적·범위·제외·Phase·자체 테스트·QA 관점
- 역할별 exact native 모델 라우팅: Sol Lead, Terra ROUTINE, Luna COMPLEX, 새 Sol QA
- host actual ID 미노출·불일치와 Luna 부재는 `BLOCKED` 또는 재분해

## 바로잡은 설계

- PLAN 문서에 실행 모델과 QA 결과를 미리 쓰지 않는다.
- Python 문자열 검증으로 runtime 모델을 검증하는 척하지 않는다.
- scope 검사는 aggregate diff가 아니라 Worker별 격리 worktree diff를 한 unit씩 검사한다.
- COMMON·INTEGRATION을 무소유 예외로 두지 않고 직렬 scope unit으로 선언한다.
- V1과 V2는 trigger와 출력 파일군을 분리해 병행한다.

상태 머신·evidence DB·다중 잠금·workspace ID는 범위 밖으로 유지한다.
