from __future__ import annotations

from pathlib import Path

import json
import yaml

from scripts.plan_core import (
    apply_event,
    apply_event_atomic,
    build_plan_content,
    evidence_ref,
    parse_plan,
    text_sha256,
    validate_structural,
)
from scripts.workspace_guard import DEFAULT_IGNORES, create_manifest


def make_plan(tmp_path: Path, complete_spec: dict) -> Path:
    plan_dir = tmp_path / "dev-plan"
    plan_dir.mkdir()
    path = plan_dir / "implement_20260725_120004.md"
    path.write_text(
        build_plan_content(
            filename=path.name,
            plan_id="PLAN-20260725-120004",
            created_at="2026-07-25T12:00:04+09:00",
            spec=complete_spec,
            lead_model="gpt-5.6-sol",
            qa_model="gpt-5.6-sol",
            isolation_mode="MANIFEST_GUARDED",
        ),
        encoding="utf-8",
    )
    return path


def make_evidence(tmp_path: Path, relative: str, content: str = "evidence\n") -> dict:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return evidence_ref(relative, project_root=tmp_path)


def make_baseline_evidence(tmp_path: Path, relative: str, plan_id: str) -> dict:
    artifact_relative = str(Path(relative).parent / "workspace.json")
    artifact = tmp_path / artifact_relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    workspace_manifest = create_manifest(tmp_path, list(DEFAULT_IGNORES))
    artifact.write_text(json.dumps(workspace_manifest, indent=2) + "\n", encoding="utf-8")
    artifact_ref = evidence_ref(artifact_relative, project_root=tmp_path)
    content = yaml.safe_dump(
        {
            "manifest_version": "codex-evidence-manifest/v1",
            "plan_id": plan_id,
            "entity_id": "PLAN",
            "attempt": 0,
            "stage": "BASELINE",
            "created_at": "2026-07-25T12:00:04+09:00",
            "validity": "VALID",
            "output_state_id": workspace_manifest["state_id"],
            "files": [{"role": "workspace_manifest", **artifact_ref}],
        },
        sort_keys=False,
    )
    return make_evidence(tmp_path, relative, content)


def fake_ref(path: str, digit: str) -> dict:
    return {"path": path, "sha256": digit * 64, "bytes": 1}


def test_atomic_event_dry_run_history_and_cas(tmp_path: Path, complete_spec: dict) -> None:
    plan = make_plan(tmp_path, complete_spec)
    planning_ref = make_baseline_evidence(
        tmp_path,
        "dev-plan/evidence/PLAN-20260725-120004/baseline/planning.txt",
        "PLAN-20260725-120004",
    )
    event = {
        "event": "PLAN_READY",
        "payload": {
            "planning_revision": (
                "manifest:"
                + yaml.safe_load((tmp_path / planning_ref["path"]).read_text(encoding="utf-8"))["output_state_id"]
            ),
            "planning_evidence": planning_ref,
        },
    }
    original = plan.read_text(encoding="utf-8")
    sha = text_sha256(original)
    preview, diff = apply_event_atomic(
        plan,
        event,
        expected_sha256=sha,
        expected_document_version=0,
        dry_run=True,
    )
    assert preview.metadata["status"] == "READY"
    assert "+status: READY" in diff
    assert plan.read_text(encoding="utf-8") == original

    updated, _ = apply_event_atomic(
        plan,
        event,
        expected_sha256=sha,
        expected_document_version=0,
    )
    assert updated.metadata["document_version"] == 1
    assert parse_plan(plan).metadata["status"] == "READY"
    history = list(
        (tmp_path / "dev-plan" / "evidence" / "PLAN-20260725-120004" / "state-history").glob("*.md")
    )
    assert len(history) == 1
    assert history[0].read_text(encoding="utf-8") == original

    current = plan.read_bytes()
    try:
        apply_event_atomic(
            plan,
            event,
            expected_sha256=sha,
            expected_document_version=0,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "CAS_MISMATCH"
    else:
        raise AssertionError("stale CAS was accepted")
    assert plan.read_bytes() == current


def test_full_single_phase_state_machine(tmp_path: Path, complete_spec: dict) -> None:
    plan = make_plan(tmp_path, complete_spec)
    doc = parse_plan(plan)

    events = [
        {
            "event": "PLAN_READY",
            "payload": {
                "planning_revision": "git:abc",
                "planning_evidence": fake_ref("planning", "a"),
            },
        },
        {
            "event": "EXECUTION_STARTED",
            "payload": {
                "execution_baseline": "git:def",
                "execution_evidence": fake_ref("execution", "b"),
            },
        },
        {
            "event": "TASK_ASSIGNED",
            "payload": {
                "task_id": "DEV-101",
                "worker_tier": "TERRA",
                "assigned_model": "gpt-5.6-terra",
                "agent_id": "worker-1",
                "input_state_id": "state-1",
                "contract_manifest": fake_ref("contract", "c"),
                "lease_expires_at": "2099-07-25T13:00:00+09:00",
                "workspace_root": "/tmp/worker-1",
                "workspace_id": "workspace-worker-1",
                "runtime_attestation": fake_ref("worker-attestation", "7"),
            },
        },
        {
            "event": "TASK_STARTED",
            "payload": {
                "task_id": "DEV-101",
                "attempt": 1,
                "agent_id": "worker-1",
                "input_state_id": "state-1",
                "lease_expires_at": "2099-07-25T13:00:00+09:00",
            },
        },
        {
            "event": "TEST_STARTED",
            "payload": {
                "test_id": "TEST-101",
                "task_refs": ["DEV-101"],
                "tested_state_id": "state-2",
                "command_sha256": doc.entity("TEST-101").data["command_sha256"],
                "input_manifest": fake_ref("test-input", "d"),
                "deadline": "2026-07-25T13:00:00+09:00",
            },
        },
        {
            "event": "TEST_REPORTED",
            "payload": {
                "test_id": "TEST-101",
                "result": "PASS",
                "actual": "exit 0",
                "evidence_manifest": fake_ref("test-result", "e"),
            },
        },
        {
            "event": "WORKER_REPORTED",
            "payload": {
                "task_id": "DEV-101",
                "output_state_id": "state-2",
                "evidence_manifest": fake_ref("worker-result", "f"),
            },
        },
        {
            "event": "PHASE_QA_STARTED",
            "payload": {
                "phase_id": "P1",
                "qa_id": "QA-101",
                "agent_id": "qa-1",
                "requested_model": "gpt-5.6-sol",
                "actual_model": "gpt-5.6-sol",
                "context_mode": "NONE",
                "input_state_id": "state-2",
                "input_manifest": fake_ref("qa-input", "1"),
                "deadline": "2026-07-25T13:00:00+09:00",
                "workspace_root": "/tmp/qa-1",
                "workspace_id": "workspace-qa-1",
                "runtime_attestation": fake_ref("qa-attestation", "8"),
            },
        },
        {
            "event": "PHASE_QA_REPORTED",
            "payload": {
                "qa_id": "QA-101",
                "verdict": "PASS",
                "evidence_manifest": fake_ref("qa-result", "2"),
                "findings": [],
            },
        },
        {
            "event": "PHASE_APPROVED",
            "payload": {
                "phase_id": "P1",
                "input_state_id": "state-2",
                "approval_evidence": fake_ref("phase-approval", "5"),
                "integration_manifest": fake_ref("integration-manifest", "0"),
                "integration_journal": fake_ref("integration-journal", "a"),
            },
        },
        {
            "event": "PLAN_QA_STARTED",
            "payload": {
                "qa_id": "QA-FINAL",
                "agent_id": "qa-final",
                "requested_model": "gpt-5.6-sol",
                "actual_model": "gpt-5.6-sol",
                "context_mode": "NONE",
                "input_state_id": "state-2",
                "input_manifest": fake_ref("final-input", "3"),
                "deadline": "2026-07-25T13:00:00+09:00",
                "workspace_root": "/tmp/qa-final",
                "workspace_id": "workspace-qa-final",
                "runtime_attestation": fake_ref("qa-final-attestation", "9"),
            },
        },
        {
            "event": "FINAL_QA_REPORTED",
            "payload": {
                "qa_id": "QA-FINAL",
                "verdict": "PASS",
                "evidence_manifest": fake_ref("final-result", "4"),
                "findings": [],
            },
        },
        {
            "event": "PLAN_APPROVED",
            "payload": {
                "input_state_id": "state-2",
                "residual_risks": [],
                "approval_evidence": fake_ref("plan-approval", "6"),
            },
        },
    ]
    for event in events:
        apply_event(doc, event, verify_evidence=False)
        rendered = doc.render()
        parsed = parse_plan(plan, text=rendered)
        errors = validate_structural(parsed)
        assert not errors, (event["event"], [error.as_dict() for error in errors])
        doc = parsed
    assert doc.metadata["status"] == "COMPLETED"
    assert doc.entity("P1").data["status"] == "DONE"
    assert doc.entity("DEV-101").data["status"] == "DONE"
    assert doc.entity("QA-FINAL").data["verdict"] == "PASS"
