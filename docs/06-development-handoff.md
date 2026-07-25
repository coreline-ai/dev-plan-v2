# 개발 핸드오프

## 유지보수 원칙

- 런타임 복잡성은 늘리지 않되 v1 계획 규약은 축소하지 않는다.
- 새 기능은 먼저 계획 템플릿·검증기·SKILL 지침으로 해결할 수 있는지 판단한다.
- 상태 DB, evidence schema, lock protocol은 기본 기능으로 추가하지 않는다.
- 모델 라우팅은 항상 명시한다: Lead/QA Sol, ROUTINE Terra, COMPLEX Luna.
- Luna가 없으면 모델을 숨겨 대체하지 않고 BLOCKED 또는 재분해한다.

## 패키징

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```

전역 설치와 실제 프로젝트 실행은 사용자의 별도 요청으로만 수행한다.
