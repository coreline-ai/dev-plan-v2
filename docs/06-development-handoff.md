# 개발 핸드오프

- 일반 계획과 결합 작업은 V1을 사용한다.
- 명시적 병렬 요청도 ASSESS 결과가 안전할 때만 V2 계획을 만든다.
- JSON이 정본이고 Markdown은 표현 문서다.
- 사용자 변경은 자동 stash·commit하지 않는다.
- COMMON 이후 lane baseline, per-worktree scope, 실제 테스트, 위험도별 QA가 모두 필요하다.
- 모델 metadata는 compliance가 요구할 때만 완료 gate다.

패키징은 빈 출력 디렉터리에서 수행한다.

```text
python3.11 scripts/package_skill.py --output <empty-dir>
```
