from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.plan_core import (
    apply_event,
    apply_event_atomic,
    build_plan_content,
    command_digest,
    evidence_ref,
    parse_plan,
    text_sha256,
    validate_approval_evidence_reference,
    validate_evidence_manifest_reference,
    validate_executable,
    validate_runtime_attestation_reference,
    validate_structural,
)
from scripts.workspace_guard import DEFAULT_IGNORES, create_manifest


def write_plan(tmp_path: Path, spec: dict, stamp: str = "20260725_120006") -> Path:
    plan_dir = tmp_path / "dev-plan"
    plan_dir.mkdir(exist_ok=True)
    path = plan_dir / f"implement_{stamp}.md"
    path.write_text(
        build_plan_content(
            filename=path.name,
            plan_id=f"PLAN-{stamp.replace('_', '-')}",
            created_at="2026-07-25T12:00:06+09:00",
            spec=spec,
            lead_model="gpt-5.6-sol",
            qa_model="gpt-5.6-sol",
            isolation_mode="MANIFEST_GUARDED",
        ),
        encoding="utf-8",
    )
    return path


def fake_ref(path: str, digit: str = "a") -> dict:
    return {"path": path, "sha256": digit * 64, "bytes": 1}


def test_plan_ready_event_rejects_unresolved_placeholders(tmp_path: Path) -> None:
    plan = write_plan(tmp_path, {})
    manifest = tmp_path / "dev-plan" / "evidence" / "PLAN-20260725-120006" / "baseline" / "plan.yaml"
    manifest.parent.mkdir(parents=True)
    workspace = manifest.parent / "workspace.json"
    workspace_manifest = create_manifest(tmp_path, list(DEFAULT_IGNORES))
    workspace.write_text(json.dumps(workspace_manifest, indent=2) + "\n", encoding="utf-8")
    workspace_reference = evidence_ref(
        "dev-plan/evidence/PLAN-20260725-120006/baseline/workspace.json",
        project_root=tmp_path,
    )
    manifest.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "codex-evidence-manifest/v1",
                "plan_id": "PLAN-20260725-120006",
                "entity_id": "PLAN",
                "attempt": 0,
                "stage": "BASELINE",
                "created_at": "2026-07-25T12:00:06+09:00",
                "validity": "VALID",
                "output_state_id": workspace_manifest["state_id"],
                "files": [{"role": "workspace_manifest", **workspace_reference}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    event = {
        "event": "PLAN_READY",
        "payload": {
            "planning_revision": f"manifest:{workspace_manifest['state_id']}",
            "planning_evidence": evidence_ref(
                "dev-plan/evidence/PLAN-20260725-120006/baseline/plan.yaml",
                project_root=tmp_path,
            ),
        },
    }
    before = plan.read_bytes()
    with pytest.raises(Exception) as caught:
        apply_event_atomic(
            plan,
            event,
            expected_sha256=text_sha256(before.decode()),
            expected_document_version=0,
        )
    assert getattr(caught.value, "code", None) == "PLACEHOLDER_FOUND"
    assert plan.read_bytes() == before


def test_task_assignment_requires_completed_dependencies(tmp_path: Path, complete_spec: dict) -> None:
    second = {
        **complete_spec["phases"][0]["tasks"][0],
        "title": "의존 태스크",
        "objective": "선행 태스크 이후 실행한다.",
        "dependencies": ["DEV-101"],
    }
    spec = {**complete_spec, "phases": [{**complete_spec["phases"][0], "tasks": [complete_spec["phases"][0]["tasks"][0], second]}]}
    doc = parse_plan(write_plan(tmp_path, spec))
    apply_event(
        doc,
        {"event": "PLAN_READY", "payload": {"planning_revision": "git:a", "planning_evidence": fake_ref("p")}},
        verify_evidence=False,
    )
    apply_event(
        doc,
        {"event": "EXECUTION_STARTED", "payload": {"execution_baseline": "git:b", "execution_evidence": fake_ref("e", "b")}},
        verify_evidence=False,
    )
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "TASK_ASSIGNED",
                "payload": {
                    "task_id": "DEV-102",
                    "worker_tier": "TERRA",
                    "assigned_model": "gpt-5.6-terra",
                    "agent_id": "worker-2",
                    "input_state_id": "state-1",
                    "contract_manifest": fake_ref("contract", "c"),
                    "lease_expires_at": "2026-07-25T13:00:00+09:00",
                    "workspace_root": "/tmp/worker-2",
                    "workspace_id": "worker-2",
                    "runtime_attestation": fake_ref("attestation", "d"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"


def test_executable_rejects_symlink_scope_escape(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "scripts").symlink_to(outside, target_is_directory=True)
    plan = write_plan(tmp_path, complete_spec)
    doc = parse_plan(plan)
    doc.metadata["status"] = "READY"
    doc.metadata["planning_revision"] = "git:a"
    doc.metadata["planning_evidence"] = fake_ref("baseline")
    codes = {error.code for error in validate_executable(doc, check_evidence=False)}
    assert "PATH_BOUNDARY_INVALID" in codes


def test_executable_rejects_empty_manual_test(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    spec = complete_spec
    test = spec["phases"][0]["tasks"][0]["tests"][0]
    test.clear()
    test.update(
        {
            "title": "수동 확인",
            "kind": "manual",
            "steps": [],
            "evidence_required": [],
            "expected": "명시된 결과",
        }
    )
    doc = parse_plan(write_plan(tmp_path, spec))
    doc.metadata["status"] = "READY"
    doc.metadata["planning_revision"] = "git:a"
    doc.metadata["planning_evidence"] = fake_ref("baseline")
    codes = {error.code for error in validate_executable(doc, check_evidence=False)}
    assert "MANUAL_STEPS_INVALID" in codes
    assert "MANUAL_EVIDENCE_INVALID" in codes


def test_phase_qa_events_reject_qa_final_aliasing(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    doc.metadata["status"] = "IN_PROGRESS"
    doc.metadata["current_phase"] = "P1"
    doc.entity("P1").data["status"] = "IN_PROGRESS"
    doc.entity("DEV-101").data["status"] = "WORKER_DONE"
    doc.entity("TEST-101").data["status"] = "PASS"
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "PHASE_QA_STARTED",
                "payload": {
                    "phase_id": "P1",
                    "qa_id": "QA-FINAL",
                    "agent_id": "qa-final-too-early",
                    "requested_model": "gpt-5.6-sol",
                    "context_mode": "NONE",
                    "input_state_id": "state-1",
                    "input_manifest": fake_ref("qa-final-input"),
                    "deadline": "2026-07-25T13:00:00+09:00",
                    "workspace_root": "/tmp/qa-final",
                    "workspace_id": "qa-final",
                    "runtime_attestation": fake_ref("qa-final-attestation"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "EVENT_PAYLOAD_INVALID"


def test_rejected_event_does_not_mutate_document(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    doc.metadata["status"] = "IN_PROGRESS"
    doc.metadata["current_phase"] = "P1"
    doc.entity("P1").data["status"] = "IN_PROGRESS"
    doc.entity("DEV-101").data["status"] = "WORKER_DONE"
    doc.entity("TEST-101").data["status"] = "PASS"
    before = doc.render()
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "PHASE_QA_STARTED",
                "payload": {
                    "phase_id": "P1",
                    "qa_id": "QA-101",
                    "agent_id": "qa-1",
                    "requested_model": "wrong-model",
                    "context_mode": "NONE",
                    "input_state_id": "state-1",
                    "input_manifest": fake_ref("qa-input"),
                    "deadline": "2099-07-25T13:00:00+09:00",
                    "workspace_root": "/tmp/qa-1",
                    "workspace_id": "qa-1",
                    "runtime_attestation": fake_ref("qa-attestation"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"
    assert doc.render() == before


def test_worker_report_rejects_expired_lease_without_mutation(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    doc.metadata["status"] = "IN_PROGRESS"
    doc.metadata["current_phase"] = "P1"
    doc.entity("P1").data["status"] = "IN_PROGRESS"
    task = doc.entity("DEV-101")
    task.data["status"] = "IN_PROGRESS"
    task.data["attempt"] = 1
    task.data["worker_tier"] = "TERRA"
    task.data["assigned_model"] = "gpt-5.6-terra"
    task.data["current_run"] = {
        "attempt": 1,
        "agent_id": "worker-1",
        "context_mode": "NONE",
        "input_state_id": "state-1",
        "lease_expires_at": "2000-01-01T00:00:00+00:00",
        "contract_manifest": fake_ref("worker-input"),
        "workspace_root": "/tmp/worker-1",
        "workspace_id": "worker-1",
        "runtime_attestation": fake_ref("worker-attestation"),
        "addresses_findings": [],
    }
    test = doc.entity("TEST-101")
    test.data["status"] = "PASS"
    test.data["results"] = [
        {
            "attempt": 1,
            "validity": "VALID",
            "tested_state_id": "state-2",
            "evidence_manifest": fake_ref("test-result"),
        }
    ]
    before = doc.render()
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "WORKER_REPORTED",
                "payload": {
                    "task_id": "DEV-101",
                    "output_state_id": "state-2",
                    "evidence_manifest": fake_ref("worker-result"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"
    assert doc.render() == before


def test_phase_qa_requires_worker_output_to_reach_aggregate_state(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    doc.metadata["status"] = "IN_PROGRESS"
    doc.metadata["current_phase"] = "P1"
    doc.entity("P1").data["status"] = "IN_PROGRESS"
    task = doc.entity("DEV-101")
    task.data["status"] = "WORKER_DONE"
    task.data["attempt"] = 1
    task.data["attempts"] = [
        {
            "attempt": 1,
            "validity": "VALID",
            "input_state_id": "state-1",
            "output_state_id": "worker-state",
            "evidence_manifest": fake_ref("worker-result"),
        }
    ]
    doc.entity("TEST-101").data["status"] = "PASS"
    before = doc.render()
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "PHASE_QA_STARTED",
                "payload": {
                    "phase_id": "P1",
                    "qa_id": "QA-101",
                    "agent_id": "qa-1",
                    "requested_model": "gpt-5.6-sol",
                    "context_mode": "NONE",
                    "input_state_id": "unrelated-state",
                    "input_manifest": fake_ref("qa-input"),
                    "deadline": "2099-07-25T13:00:00+09:00",
                    "workspace_root": "/tmp/qa-1",
                    "workspace_id": "qa-1",
                    "runtime_attestation": fake_ref("qa-attestation"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "EVIDENCE_STATE_MISMATCH"
    assert doc.render() == before


def test_finding_resolution_requires_worker_and_qa_linkage(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    finding_ref = "QA-101/A0001/F001"
    report_ref = fake_ref("qa-pass")
    doc.metadata["finding_ledger"] = [
        {
            "finding_ref": finding_ref,
            "severity": "major",
            "status": "OPEN",
            "opened_by": {"report_manifest": fake_ref("qa-fail")},
            "summary": "재현 가능한 결함",
            "related_entities": ["P1", "DEV-101"],
            "addressed_by": [],
            "resolved_by": "NONE",
        }
    ]
    qa = doc.entity("QA-101")
    qa.data["status"] = "FINISHED"
    qa.data["verdict"] = "PASS"
    qa.data["current_attempt"] = 1
    qa.data["attempts"] = [
        {
            "attempt": 1,
            "validity": "VALID",
            "verdict": "PASS",
            "input_state_id": "state-fixed",
            "resolved_findings": [finding_ref],
            "evidence_manifest": report_ref,
        }
    ]
    event = {
        "event": "FINDING_RESOLVED",
        "payload": {
            "finding_ref": finding_ref,
            "qa_id": "QA-101",
            "input_state_id": "state-fixed",
            "resolution_evidence": fake_ref("resolution"),
        },
    }
    with pytest.raises(Exception) as caught:
        apply_event(doc, event, verify_evidence=False)
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"

    task = doc.entity("DEV-101")
    worker_report = fake_ref("worker-report")
    task.data["attempts"] = [
        {
            "attempt": 0,
            "validity": "STALE",
            "addresses_findings": [finding_ref],
            "evidence_manifest": fake_ref("stale-worker-report"),
        },
        {
            "attempt": 1,
            "validity": "VALID",
            "addresses_findings": [finding_ref],
            "evidence_manifest": worker_report,
        }
    ]
    doc.metadata["finding_ledger"][0]["addressed_by"] = [
        {
            "task_id": "DEV-101",
            "attempt": 0,
            "report_manifest": fake_ref("stale-worker-report"),
        },
        {
            "task_id": "DEV-101",
            "attempt": 1,
            "report_manifest": worker_report,
        }
    ]
    apply_event(doc, event, verify_evidence=False)
    assert doc.metadata["finding_ledger"][0]["status"] == "RESOLVED"


def test_block_events_require_real_blocked_state(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "BLOCK_CLEARED",
                "payload": {
                    "entity_ids": ["DEV-101"],
                    "phase_ids": ["P1"],
                    "resolution_evidence": fake_ref("resolution"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "EVENT_FROM_MISMATCH"

    cascade_root = tmp_path / "cascade"
    cascade_root.mkdir()
    doc = parse_plan(write_plan(cascade_root, complete_spec, stamp="20260725_120016"))
    apply_event(
        doc,
        {
            "event": "ENTITY_BLOCKED",
            "payload": {
                "entity_id": "DEV-101",
                "reason": "작업 입력 불일치",
                "unblock_conditions": ["입력 상태를 다시 검증한다."],
            },
        },
        verify_evidence=False,
    )
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "BLOCK_CLEARED",
                "payload": {
                    "entity_ids": [],
                    "phase_ids": ["P1"],
                    "resolution_evidence": fake_ref("resolution"),
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"

    doc.metadata["status"] = "COMPLETED"
    doc.metadata["current_phase"] = "NONE"
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "ENTITY_BLOCKED",
                "payload": {
                    "entity_id": "DEV-101",
                    "reason": "완료 후 회귀 시도",
                    "unblock_conditions": ["허용하지 않는다."],
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "EVENT_FROM_MISMATCH"


def test_inline_command_wrappers_are_rejected(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    plan = write_plan(tmp_path, complete_spec)
    doc = parse_plan(plan)
    doc.metadata["status"] = "READY"
    doc.metadata["planning_revision"] = "git:a"
    doc.metadata["planning_evidence"] = fake_ref("baseline")
    test = doc.entity("TEST-101")
    test.data["argv"] = ["env", "python3.12", "-c", "print('no')"]
    test.data["command_sha256"] = command_digest(test.data)
    codes = {error.code for error in validate_executable(doc, check_evidence=False)}
    assert "INLINE_COMMAND_FORBIDDEN" in codes


def test_assignment_lease_identity_and_path_conflict_guards(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    second = {
        **complete_spec["phases"][0]["tasks"][0],
        "title": "동일 경로 작업",
        "objective": "동일 경로를 수정한다.",
        "dependencies": [],
    }
    third = {
        **complete_spec["phases"][0]["tasks"][0],
        "title": "세 번째 동일 경로 작업",
        "objective": "직렬 상태 체인의 세 번째 변경을 수행한다.",
        "dependencies": [],
    }
    spec = {
        **complete_spec,
        "phases": [
            {
                **complete_spec["phases"][0],
                "tasks": [complete_spec["phases"][0]["tasks"][0], second, third],
            }
        ],
    }
    doc = parse_plan(write_plan(tmp_path, spec))
    apply_event(
        doc,
        {"event": "PLAN_READY", "payload": {"planning_revision": "git:a", "planning_evidence": fake_ref("p")}},
        verify_evidence=False,
    )
    apply_event(
        doc,
        {"event": "EXECUTION_STARTED", "payload": {"execution_baseline": "git:b", "execution_evidence": fake_ref("e")}},
        verify_evidence=False,
    )

    def assignment(task_id: str, agent_id: str, lease: str) -> dict:
        return {
            "event": "TASK_ASSIGNED",
            "payload": {
                "task_id": task_id,
                "worker_tier": "TERRA",
                "assigned_model": "gpt-5.6-terra",
                "agent_id": agent_id,
                "input_state_id": "state-1",
                "contract_manifest": fake_ref(f"{task_id}-input"),
                "lease_expires_at": lease,
                "workspace_root": f"/tmp/{agent_id}",
                "workspace_id": agent_id,
                "runtime_attestation": fake_ref(f"{task_id}-attestation"),
            },
        }

    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            assignment("DEV-101", "worker-expired", "2000-01-01T00:00:00+00:00"),
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "EVENT_PAYLOAD_INVALID"

    valid = assignment("DEV-101", "worker-1", "2099-01-01T00:00:00+00:00")
    apply_event(doc, valid, verify_evidence=False)
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "TASK_STARTED",
                "payload": {
                    "task_id": "DEV-101",
                    "attempt": 999,
                    "agent_id": "worker-1",
                    "input_state_id": "wrong",
                    "lease_expires_at": "2099-01-01T00:00:00+00:00",
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            {
                "event": "WORKER_ATTEMPT_INVALIDATED",
                "payload": {
                    "task_id": "DEV-101",
                    "attempt": 999,
                    "agent_id": "worker-old",
                    "input_state_id": "old-state",
                    "reason": "stale timeout replay",
                },
            },
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"
    assert doc.entity("DEV-101").data["status"] == "ASSIGNED"
    with pytest.raises(Exception) as caught:
        apply_event(
            doc,
            assignment("DEV-102", "worker-2", "2099-01-01T00:00:00+00:00"),
            verify_evidence=False,
        )
    assert getattr(caught.value, "code", None) == "GUARD_FAILED"

    first = doc.entity("DEV-101")
    first.data["status"] = "WORKER_DONE"
    first.data["current_run"] = "NONE"
    first.data["attempts"] = [
        {
            "attempt": 1,
            "validity": "VALID",
            "input_state_id": "state-1",
            "output_state_id": "state-2",
            "evidence_manifest": fake_ref("worker-result"),
        }
    ]
    chained = assignment("DEV-102", "worker-2", "2099-01-01T00:00:00+00:00")
    chained["payload"]["input_state_id"] = "state-2"
    apply_event(doc, chained, verify_evidence=False)
    assert doc.entity("DEV-102").data["status"] == "ASSIGNED"

    second_block = doc.entity("DEV-102")
    second_block.data["status"] = "WORKER_DONE"
    second_block.data["current_run"] = "NONE"
    second_block.data["attempts"] = [
        {
            "attempt": 1,
            "validity": "VALID",
            "input_state_id": "state-2",
            "output_state_id": "state-3",
            "evidence_manifest": fake_ref("worker-result-2"),
        }
    ]
    third_event = assignment("DEV-103", "worker-3", "2099-01-01T00:00:00+00:00")
    third_event["payload"]["input_state_id"] = "state-3"
    apply_event(doc, third_event, verify_evidence=False)
    assert doc.entity("DEV-103").data["status"] == "ASSIGNED"


def test_evidence_manifest_requires_entity_specific_roles(
    tmp_path: Path,
) -> None:
    plan_id = "PLAN-20260725-120006"
    evidence_root = tmp_path / "dev-plan" / "evidence" / plan_id / "DEV-101" / "attempt-0001"
    evidence_root.mkdir(parents=True)
    dummy = evidence_root / "dummy.txt"
    dummy.write_text("dummy\n", encoding="utf-8")
    workspace = evidence_root / "workspace.json"
    workspace.write_text("{}\n", encoding="utf-8")
    contract = evidence_root / "worker-contract.yaml"
    contract.write_text("contract: true\n", encoding="utf-8")
    input_path = evidence_root / "input-manifest.yaml"
    input_files = [
        {"role": "workspace_manifest", **evidence_ref(str(workspace.relative_to(tmp_path)), project_root=tmp_path)},
        {"role": "worker_contract", **evidence_ref(str(contract.relative_to(tmp_path)), project_root=tmp_path)},
    ]
    input_files.sort(key=lambda item: item["path"])
    input_path.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "codex-evidence-manifest/v1",
                "plan_id": plan_id,
                "entity_id": "DEV-101",
                "attempt": 1,
                "stage": "INPUT",
                "created_at": "2026-07-25T12:00:00+09:00",
                "validity": "VALID",
                "input_state_id": "state-1",
                "files": input_files,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    result_path = evidence_root / "result-manifest.yaml"
    result_path.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "codex-evidence-manifest/v1",
                "plan_id": plan_id,
                "entity_id": "DEV-101",
                "attempt": 1,
                "stage": "RESULT",
                "created_at": "2026-07-25T12:01:00+09:00",
                "validity": "VALID",
                "input_state_id": "state-1",
                "output_state_id": "state-2",
                "input_manifest": evidence_ref(
                    str(input_path.relative_to(tmp_path)),
                    project_root=tmp_path,
                ),
                "files": [
                    {
                        "role": "dummy_result",
                        **evidence_ref(str(dummy.relative_to(tmp_path)), project_root=tmp_path),
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    errors = validate_evidence_manifest_reference(
        evidence_ref(str(result_path.relative_to(tmp_path)), project_root=tmp_path),
        project_root=tmp_path,
        expected_plan_id=plan_id,
        expected_entity_id="DEV-101",
        expected_stage="RESULT",
        expected_attempt=1,
    )
    assert any(error.code == "EVIDENCE_MANIFEST_INVALID" for error in errors)

    role_files = []
    role_paths: dict[str, Path] = {}
    for role in ("worker_report", "pre_state", "post_state", "diff", "test_log"):
        role_path = evidence_root / f"{role}.txt"
        role_path.write_text(f"{role}\n", encoding="utf-8")
        role_paths[role] = role_path
        role_files.append(
            {
                "role": role,
                **evidence_ref(str(role_path.relative_to(tmp_path)), project_root=tmp_path),
            }
        )
    role_files.sort(key=lambda item: item["path"])
    result_path.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "codex-evidence-manifest/v1",
                "plan_id": plan_id,
                "entity_id": "DEV-101",
                "attempt": 1,
                "stage": "RESULT",
                "created_at": "2026-07-25T12:01:00+09:00",
                "validity": "VALID",
                "input_state_id": "state-1",
                "output_state_id": "state-2",
                "input_manifest": evidence_ref(
                    str(input_path.relative_to(tmp_path)),
                    project_root=tmp_path,
                ),
                "files": role_files,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    outer_ref = evidence_ref(str(result_path.relative_to(tmp_path)), project_root=tmp_path)
    role_paths["diff"].unlink()
    nested_errors = validate_evidence_manifest_reference(
        outer_ref,
        project_root=tmp_path,
        expected_plan_id=plan_id,
        expected_entity_id="DEV-101",
        expected_stage="RESULT",
        expected_attempt=1,
    )
    assert any(error.code == "EVIDENCE_MISSING" for error in nested_errors)


def test_workspace_identity_and_spawn_artifacts_are_bound(
    tmp_path: Path,
) -> None:
    plan_id = "PLAN-20260725-120007"
    workspace_root = tmp_path / "worker"
    workspace_root.mkdir()
    (workspace_root / "item.txt").write_text("state\n", encoding="utf-8")
    workspace_manifest = create_manifest(workspace_root, list(DEFAULT_IGNORES))
    evidence_dir = tmp_path / "dev-plan" / "evidence" / plan_id / "DEV-101" / "attempt-0001"
    evidence_dir.mkdir(parents=True)
    workspace_path = evidence_dir / "workspace.json"
    workspace_path.write_text(json.dumps(workspace_manifest) + "\n", encoding="utf-8")
    contract_path = evidence_dir / "contract.yaml"
    contract_path.write_text("contract: true\n", encoding="utf-8")
    manifest_path = evidence_dir / "input.yaml"
    files = [
        {
            "role": "workspace_manifest",
            **evidence_ref(str(workspace_path.relative_to(tmp_path)), project_root=tmp_path),
        },
        {
            "role": "worker_contract",
            **evidence_ref(str(contract_path.relative_to(tmp_path)), project_root=tmp_path),
        },
    ]
    files.sort(key=lambda item: item["path"])
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "codex-evidence-manifest/v1",
                "plan_id": plan_id,
                "entity_id": "DEV-101",
                "attempt": 1,
                "stage": "INPUT",
                "created_at": "2026-07-25T12:00:00+09:00",
                "validity": "VALID",
                "input_state_id": workspace_manifest["state_id"],
                "files": files,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    identity_errors = validate_evidence_manifest_reference(
        evidence_ref(str(manifest_path.relative_to(tmp_path)), project_root=tmp_path),
        project_root=tmp_path,
        expected_plan_id=plan_id,
        expected_entity_id="DEV-101",
        expected_stage="INPUT",
        expected_attempt=1,
        expected_workspace_root=str(tmp_path / "different-worker"),
        expected_workspace_id=workspace_manifest["workspace_id"],
    )
    assert any(error.code == "EVIDENCE_MANIFEST_INVALID" for error in identity_errors)
    disposable_errors = validate_evidence_manifest_reference(
        evidence_ref(str(manifest_path.relative_to(tmp_path)), project_root=tmp_path),
        project_root=tmp_path,
        expected_plan_id=plan_id,
        expected_entity_id="DEV-101",
        expected_stage="INPUT",
        expected_attempt=1,
        expected_workspace_root=str(workspace_root),
        expected_workspace_id=workspace_manifest["workspace_id"],
        require_disposable_workspace=True,
    )
    assert any(error.code == "WORKSPACE_NOT_DISPOSABLE" for error in disposable_errors)

    attestation_path = evidence_dir / "runtime-attestation.json"
    attestation_path.write_text(
        json.dumps(
            {
                "schema": "codex-runtime-attestation/v1",
                "agent_id": "worker-1",
                "role": "WORKER",
                "worker_tier": "TERRA",
                "requested_model": "gpt-5.6-terra",
                "actual_model": "gpt-5.6-terra",
                "supported_models": ["gpt-5.6-terra"],
                "context_mode": "NONE",
                "workspace_root": str(workspace_root),
                "workspace_id": workspace_manifest["workspace_id"],
                "spawn_receipt_sha256": "0" * 64,
                "created_at": "2026-07-25T12:00:00+09:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _, attestation_errors = validate_runtime_attestation_reference(
        evidence_ref(str(attestation_path.relative_to(tmp_path)), project_root=tmp_path),
        project_root=tmp_path,
        expected_agent_id="worker-1",
        expected_role="WORKER",
        expected_model="gpt-5.6-terra",
        expected_tier="TERRA",
    )
    assert any(error.code == "EVIDENCE_MISSING" for error in attestation_errors)


def test_accepted_risk_requires_bidirectional_ledger_entry(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    doc = parse_plan(write_plan(tmp_path, complete_spec))
    doc.metadata["finding_ledger"] = [
        {
            "finding_ref": "QA-101/A0001/F001",
            "severity": "critical",
            "status": "ACCEPTED_RISK",
            "opened_by": {"report_manifest": fake_ref("report")},
            "summary": "사용자가 수용한 위험",
            "related_entities": ["P1"],
            "addressed_by": [],
            "resolved_by": "NONE",
        }
    ]
    codes = {error.code for error in validate_structural(doc)}
    assert "RISK_INVALID" in codes

    ordinary = tmp_path / "README.txt"
    ordinary.write_text("ordinary project file, not user approval\n", encoding="utf-8")
    _, errors = validate_approval_evidence_reference(
        evidence_ref("README.txt", project_root=tmp_path),
        project_root=tmp_path,
        expected_plan_id="PLAN-20260725-120006",
        expected_kind="RISK",
        expected_entity_id="RISK-001",
        expected_approver_role="USER",
    )
    assert any(error.code == "EVIDENCE_PATH_INVALID" for error in errors)
