# 개발 핸드오프

## 유지보수 원칙

- 기능을 추가하기 전에 `SKILL.md`만으로 해결할 수 있는지 먼저 판단한다.
- 새 상태 DB, evidence schema, lock protocol은 기본 기능으로 추가하지 않는다.
- 스크립트는 표준 라이브러리와 짧은 CLI에 한정한다.
- 실행 정책은 native Codex delegation에 맡기며, 별도 API/CLI 프로세스를 만들지 않는다.

## 패키징

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```

전역 설치와 실제 프로젝트 실행은 사용자의 별도 요청으로만 수행한다.
