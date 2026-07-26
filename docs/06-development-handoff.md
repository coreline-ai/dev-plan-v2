# 개발 핸드오프

## 유지보수 원칙

- 런타임 복잡성은 늘리지 않되 v1의 계획·진행·테스트·QA 규약은 축소하지 않는다.
- 새 기능은 먼저 계획 템플릿·검증기·SKILL 지침으로 해결할 수 있는지 판단한다.
- 상태 DB, evidence schema, lock protocol은 기본 기능으로 추가하지 않는다.
- 실행 전 모델 목록을 확인하고 Lead/QA=Sol, ROUTINE=Terra, COMPLEX=Luna의 exact override를 강제한다.
- Worker와 QA는 `fork_turns: none`의 분리 컨텍스트다.
- Luna 미제공, host actual ID 미노출, requested/actual 불일치는 `BLOCKED` 또는 재분해다.

## 패키징

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```

전역 설치와 실제 프로젝트 실행은 사용자의 별도 요청으로만 수행한다.
