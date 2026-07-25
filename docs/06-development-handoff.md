# 개발 핸드오프

최종 갱신: `2026-07-25 KST`

## 1. 현재 상태

| 항목 | 상태 |
|---|---|
| 원본 저장소 | `/Volumes/Eprojects/project_202607/dev-plan-v2` |
| Git 기본 브랜치 | `main` |
| 스킬 이름·설치 폴더 | `codex-dev-plan-orchestrator` |
| 스캐폴드 | skill-creator `init_skill.py` 기반 완료 |
| SKILL·UI metadata | 구현 완료 |
| 생성·업그레이드·검증·상태 CLI | 구현 완료 |
| 공통 parser/state engine | 구현 완료 |
| 런타임 references 정본 | 이전 완료 |
| pytest·quick validation | 구현 및 실행 완료 |
| allowlist 패키징 | 구현 완료 |
| 전역 설치 | 수행하지 않음 |

현재 상태는 **원본 스킬 구현·자동 검증·독립 감사 완료, release-ready**다.
전역 설치와 외부 프로젝트 운영 파일럿은 수행하지 않았다.

## 2. 핵심 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 7개 모드와 Lead/Worker/QA 운영 지시 |
| `agents/openai.yaml` | UI 표시 이름·설명·기본 프롬프트 |
| `scripts/plan_core.py` | 제한 YAML, AST parser, serializer, 검증, 상태 이벤트, 원자 쓰기 |
| `scripts/new_dev_plan.py` | 신규 v2 DRAFT 생성 |
| `scripts/upgrade_dev_plan.py` | v1 원본 보존 업그레이드 |
| `scripts/validate_dev_plan.py` | structural/executable·candidate 검증 |
| `scripts/update_plan_state.py` | Lead event dry-run·CAS 원자 적용 |
| `scripts/workspace_guard.py` | disposable copy·범위 검사·source CAS 통합·복구 |
| `scripts/check_runtime.py` | Python·의존성 사전 점검과 설치 안내 |
| `scripts/package_skill.py` | 런타임 allowlist 패키지 생성 |
| `references/` | 스키마·워크플로·에이전트 계약 정본 |
| `tests/` | 생성·검증·상태·업그레이드·패키징 회귀 테스트 |

## 3. 구현된 안전 계약

1. 새 계획은 덮어쓰지 않고 항상 `DRAFT`로 생성한다.
2. v1 원본은 수정하지 않으며 절대 경로·SHA-256·크기를 새 문서에 기록한다.
3. YAML alias·merge·중복 키와 비안전 태그를 거부한다.
4. 실행 전 플레이스홀더·경로·명령·모델·evidence를 검사한다.
5. 상태 변경은 이벤트 allowlist만 허용한다.
6. 문서 SHA-256와 version CAS를 모두 요구한다.
7. source→evidence→plan persistent `flock` 내부에서 문서·계약·evidence를 다시 검증한다.
8. 이전 상태를 append-only history에 보존하고 `fsync`·원자 교체한다.
9. Worker output, TEST state, Phase aggregate, QA input state를 연결한다.
10. Phase 및 최종 QA PASS 없이는 승인할 수 없다.
11. finding과 accepted risk는 evidence를 통해 연결한다.
12. Worker/QA는 내장 위임만 사용하고 계획을 직접 수정하지 않는다.
13. 별도 모델 enum snapshot·spawn receipt와 workspace identity를 runtime
    attestation 및 attempt manifest에 교차 결합한다.
14. 통합 전 PREPARED journal을 저장하고 계획 승인 실패 시 source를 자동 원복한다.
15. evidence role 파일과 상위 INPUT manifest를 승인 시 재귀 재검증한다.
16. source→evidence control-plane→plan 잠금 순서로 승인 중 evidence TOCTOU를 막는다.
17. integration allowlist는 Plan Phase DEV 계약 union에서 파생하고 digest로 묶는다.
18. 모든 rejected event는 clone에서 폐기되어 caller 문서를 부분 변경하지 않는다.
19. source 통합은 Phase QA current attempt `VALID/PASS` 이후에만 허용한다.
20. `MANIFEST_GUARDED` Worker/QA workspace는 source 밖 canonical 경로만 허용하고,
    workspace ID를 canonical root SHA-256에서 재계산한다.

## 4. 유지보수 순서

1. `references/plan-schema-v2.md`에서 규격을 수정한다.
2. `scripts/plan_core.py`와 관련 CLI를 함께 수정한다.
3. 양성·음성 테스트를 추가한다.
4. `python3.11 -m pytest`를 실행한다.
5. skill-creator `quick_validate.py`를 실행한다.
6. `scripts/package_skill.py`로 새 임시 패키지를 생성한다.
7. 독립 에이전트 전방 테스트와 Git diff 검사를 수행한다.
8. 검증 결과를 `docs/07-expert-revalidation.md`에 기록한다.

## 5. 배포 절차

패키지는 기존 대상 폴더를 덮어쓰지 않는다.

```text
python3.11 scripts/package_skill.py --output <empty-output-dir>
```

산출물:

```text
<empty-output-dir>/
├── codex-dev-plan-orchestrator/
└── codex-dev-plan-orchestrator.manifest.json
```

manifest의 파일 목록·SHA-256·quick validation 결과를 확인한 후에만 별도 승인으로
`${CODEX_HOME:-$HOME/.codex}/skills/codex-dev-plan-orchestrator/`에 설치한다.

## 6. 잔여 운영 제약

- 현재 확인된 Worker는 Terra이며 Luna는 확인되지 않았다.
- `MANIFEST_GUARDED`는 hostile sandbox가 아니라 협력적 무결성 모델이다.
- 실제 Worker 실행 전 disposable workspace, 전체 manifest, inventory, lock,
  preimage CAS를 준비해야 한다.
- Worker·Phase QA·최종 QA workspace가 source 또는 그 하위이면 실행하지 않는다.
- 설치 환경에는 Python 3.11+, POSIX `flock`, PyYAML 6.x,
  markdown-it-py 4.x가 필요하다.
- 전역 설치와 실제 외부 프로젝트 실행은 사용자의 별도 실행 요청 범위다.
