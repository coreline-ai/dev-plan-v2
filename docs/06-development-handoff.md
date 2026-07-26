# 개발 핸드오프

- 일반 계획은 V1을 사용하고, V2는 `병렬개발계획` 또는 명시 호출에서만 사용한다.
- V2는 `dev-plan/parallel/parallel_*.md`만 만들며 V1 `implement_*.md`를 수정하지 않는다.
- `PLAN`은 실행 모델·host 결과·QA 결과를 기록하지 않는다.
- `EXECUTE`는 clean baseline, 격리 worktree, per-unit scope check, 실제 테스트, 독립 QA가 모두 필요하다.
- native delegation smoke는 Python/pytest가 대체할 수 없다.

패키징은 빈 출력 디렉터리에서 수행한다.

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```
