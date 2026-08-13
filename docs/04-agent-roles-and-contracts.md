# 역할·범위·보고 규약

| 역할 | 책임 | 경계 |
|---|---|---|
| Lead | 의미적 결합 평가, baseline, worktree, 통합, 증거 확인 | 병렬화를 위해 책임을 억지 분할하지 않음 |
| Worker | 한 scope unit 구현과 테스트 | 자기 worktree와 write 경로 밖 수정 금지 |
| Reviewer | 실제 diff·scope·테스트 독립 검토 | Worker 자기평가를 완료 근거로 사용하지 않음 |
| 사용자·전문가 | critical 위험 승인 | 필요한 도메인·보안 판단 제공 |

모델 제품명은 역할 계약이 아니다. Worker 요청에는 goal, write paths, read context, tests, risk, 완료 조건과 필요한 capabilities만 전달한다.
