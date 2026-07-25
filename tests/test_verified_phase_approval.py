from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.plan_core import (
    apply_event_atomic,
    build_plan_content,
    evidence_ref,
    parse_plan,
    text_sha256,
)
from scripts.workspace_guard import (
    DEFAULT_IGNORES,
    create_manifest,
    integrate_workspace,
    prepare_copy,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, value: dict) -> None:
    _write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _ref(root: Path, path: Path) -> dict:
    return evidence_ref(str(path.relative_to(root)), project_root=root)


def _attempt_manifest(
    *,
    root: Path,
    plan_id: str,
    entity_id: str,
    attempt: int,
    stage: str,
    input_state_id: str,
    output_state_id: str | None,
    input_manifest: dict | None,
    role_files: dict[str, Path],
) -> dict:
    directory = root / "dev-plan" / "evidence" / plan_id / entity_id / f"attempt-{attempt:04d}"
    path = directory / f"{stage.lower()}-manifest.yaml"
    files = [{"role": role, **_ref(root, artifact)} for role, artifact in role_files.items()]
    files.sort(key=lambda item: item["path"])
    value = {
        "manifest_version": "codex-evidence-manifest/v1",
        "plan_id": plan_id,
        "entity_id": entity_id,
        "attempt": attempt,
        "stage": stage,
        "created_at": "2026-07-25T12:00:00+09:00",
        "validity": "VALID",
        "input_state_id": input_state_id,
        "files": files,
    }
    if output_state_id is not None:
        value["output_state_id"] = output_state_id
    if input_manifest is not None:
        value["input_manifest"] = input_manifest
    _write(path, yaml.safe_dump(value, allow_unicode=True, sort_keys=False))
    return _ref(root, path)


def _baseline_manifest(
    root: Path,
    plan_id: str,
    name: str,
    workspace_path: Path,
    state_id: str,
) -> dict:
    path = root / "dev-plan" / "evidence" / plan_id / "baseline" / f"{name}.yaml"
    value = {
        "manifest_version": "codex-evidence-manifest/v1",
        "plan_id": plan_id,
        "entity_id": "PLAN",
        "attempt": 0,
        "stage": "BASELINE",
        "created_at": "2026-07-25T12:00:00+09:00",
        "validity": "VALID",
        "output_state_id": state_id,
        "files": [{"role": "workspace_manifest", **_ref(root, workspace_path)}],
    }
    _write(path, yaml.safe_dump(value, sort_keys=False))
    return _ref(root, path)


def _attestation(
    root: Path,
    path: Path,
    *,
    agent_id: str,
    role: str,
    model: str,
    workspace_root: str,
    workspace_id: str,
    worker_tier: str | None = None,
) -> dict:
    model_snapshot_path = path.parent / "model-enum-snapshot.json"
    _write_json(
        model_snapshot_path,
        {
            "schema": "codex-model-enum-snapshot/v1",
            "runtime_source": "native-codex-delegation-tool",
            "models": ["gpt-5.6-sol", "gpt-5.6-terra"],
            "created_at": "2026-07-25T12:00:00+09:00",
        },
    )
    spawn_receipt_path = path.parent / "spawn-receipt.json"
    _write_json(
        spawn_receipt_path,
        {
            "schema": "codex-spawn-receipt/v1",
            "status": "SPAWNED",
            "agent_id": agent_id,
            "role": role,
            "requested_model": model,
            "actual_model": model,
            "context_mode": "NONE",
            "workspace_root": workspace_root,
            "workspace_id": workspace_id,
            "created_at": "2026-07-25T12:00:00+09:00",
        },
    )
    model_snapshot_ref = _ref(root, model_snapshot_path)
    spawn_receipt_ref = _ref(root, spawn_receipt_path)
    value = {
        "schema": "codex-runtime-attestation/v1",
        "agent_id": agent_id,
        "role": role,
        "requested_model": model,
        "actual_model": model,
        "supported_models": ["gpt-5.6-sol", "gpt-5.6-terra"],
        "context_mode": "NONE",
        "workspace_root": workspace_root,
        "workspace_id": workspace_id,
        "model_enum_snapshot": model_snapshot_ref,
        "spawn_receipt": spawn_receipt_ref,
        "spawn_receipt_sha256": spawn_receipt_ref["sha256"],
        "created_at": "2026-07-25T12:00:00+09:00",
    }
    if worker_tier:
        value["worker_tier"] = worker_tier
    _write_json(path, value)
    return _ref(root, path)


def test_phase_approval_uses_real_evidence_integration_and_commit_marker(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "product.txt").write_text("before\n", encoding="utf-8")
    plan_id = "PLAN-20260725-120200"
    plan = root / "dev-plan" / "implement_20260725_120200.md"
    plan.parent.mkdir()
    plan.write_text(
        build_plan_content(
            filename=plan.name,
            plan_id=plan_id,
            created_at="2026-07-25T12:02:00+09:00",
            spec=complete_spec,
            lead_model="gpt-5.6-sol",
            qa_model="gpt-5.6-sol",
            isolation_mode="MANIFEST_GUARDED",
        ),
        encoding="utf-8",
    )

    source_baseline = create_manifest(root, list(DEFAULT_IGNORES))
    baseline_dir = root / "dev-plan" / "evidence" / plan_id / "baseline"
    source_workspace_path = baseline_dir / "workspace.json"
    _write_json(source_workspace_path, source_baseline)
    planning_ref = _baseline_manifest(
        root, plan_id, "planning", source_workspace_path, source_baseline["state_id"]
    )
    execution_ref = _baseline_manifest(
        root, plan_id, "execution", source_workspace_path, source_baseline["state_id"]
    )

    disposable = tmp_path / "worker"
    disposable_baseline_path = tmp_path / "worker-baseline.json"
    disposable_baseline = prepare_copy(root, disposable, disposable_baseline_path)
    (disposable / "scripts" / "product.txt").write_text("after\n", encoding="utf-8")
    post_workspace = create_manifest(disposable, list(DEFAULT_IGNORES))

    evidence_dir = root / "dev-plan" / "evidence" / plan_id
    pre_state_path = evidence_dir / "shared" / "pre-state.json"
    post_state_path = evidence_dir / "shared" / "post-state.json"
    _write_json(pre_state_path, disposable_baseline)
    _write_json(post_state_path, post_workspace)

    task_dir = evidence_dir / "DEV-101" / "attempt-0001"
    task_contract = task_dir / "worker-contract.yaml"
    _write(task_contract, "contract_version: codex-worker-contract/v1\n")
    task_input = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="DEV-101",
        attempt=1,
        stage="INPUT",
        input_state_id=source_baseline["state_id"],
        output_state_id=None,
        input_manifest=None,
        role_files={
            "worker_contract": task_contract,
            "workspace_manifest": pre_state_path,
        },
    )
    task_artifacts = {}
    for role in ("worker_report", "diff", "test_log"):
        artifact = task_dir / f"{role}.txt"
        _write(artifact, f"{role}\n")
        task_artifacts[role] = artifact
    task_artifacts.update({"pre_state": pre_state_path, "post_state": post_state_path})
    task_result = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="DEV-101",
        attempt=1,
        stage="RESULT",
        input_state_id=source_baseline["state_id"],
        output_state_id=post_workspace["state_id"],
        input_manifest=task_input,
        role_files=task_artifacts,
    )
    worker_attestation = _attestation(
        root,
        task_dir / "runtime-attestation.json",
        agent_id="worker-1",
        role="WORKER",
        model="gpt-5.6-terra",
        worker_tier="TERRA",
        workspace_root=str(disposable),
        workspace_id=post_workspace["workspace_id"],
    )

    test_dir = evidence_dir / "TEST-101" / "attempt-0001"
    test_input = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="TEST-101",
        attempt=1,
        stage="INPUT",
        input_state_id=post_workspace["state_id"],
        output_state_id=None,
        input_manifest=None,
        role_files={"workspace_manifest": post_state_path},
    )
    test_log = test_dir / "test.log"
    _write(test_log, "PASS\n")
    test_result = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="TEST-101",
        attempt=1,
        stage="RESULT",
        input_state_id=post_workspace["state_id"],
        output_state_id=post_workspace["state_id"],
        input_manifest=test_input,
        role_files={"test_log": test_log, "post_state": post_state_path},
    )

    qa_dir = evidence_dir / "QA-101" / "attempt-0001"
    qa_contract = qa_dir / "qa-contract.yaml"
    _write(qa_contract, "contract_version: codex-qa-contract/v1\n")
    qa_input = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="QA-101",
        attempt=1,
        stage="INPUT",
        input_state_id=post_workspace["state_id"],
        output_state_id=None,
        input_manifest=None,
        role_files={"qa_contract": qa_contract, "workspace_manifest": post_state_path},
    )
    qa_pre_state = qa_dir / "pre-state.json"
    qa_post_state = qa_dir / "post-state.json"
    _write_json(qa_pre_state, post_workspace)
    _write_json(qa_post_state, post_workspace)
    qa_artifacts = {"pre_state": qa_pre_state, "post_state": qa_post_state}
    for role in ("qa_response", "qa_report"):
        artifact = qa_dir / f"{role}.txt"
        _write(artifact, f"{role}: PASS\n")
        qa_artifacts[role] = artifact
    qa_result = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="QA-101",
        attempt=1,
        stage="RESULT",
        input_state_id=post_workspace["state_id"],
        output_state_id=post_workspace["state_id"],
        input_manifest=qa_input,
        role_files=qa_artifacts,
    )
    qa_attestation = _attestation(
        root,
        qa_dir / "runtime-attestation.json",
        agent_id="qa-1",
        role="QA",
        model="gpt-5.6-sol",
        workspace_root=str(disposable),
        workspace_id=post_workspace["workspace_id"],
    )

    approval = evidence_dir / "P1" / "approval.yaml"
    _write(
        approval,
        yaml.safe_dump(
            {
                "schema": "codex-approval-evidence/v1",
                "plan_id": plan_id,
                "approval_kind": "PHASE",
                "entity_id": "P1",
                "approver_role": "LEAD",
                "decision": "APPROVED",
                "created_at": "2026-07-25T12:05:00+09:00",
                "statement": "Phase 결과와 QA PASS를 승인한다.",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    approval_ref = _ref(root, approval)

    doc = parse_plan(plan)
    doc.metadata.update(
        {
            "status": "IN_PROGRESS",
            "current_phase": "P1",
            "document_version": 7,
            "planning_revision": f"manifest:{source_baseline['state_id']}",
            "planning_evidence": planning_ref,
            "execution_baseline": f"manifest:{source_baseline['state_id']}",
            "execution_evidence": execution_ref,
        }
    )
    phase = doc.entity("P1")
    phase.data["status"] = "QA"
    task = doc.entity("DEV-101")
    task.data.update(
        {
            "status": "WORKER_DONE",
            "attempt": 1,
            "worker_tier": "TERRA",
            "assigned_model": "gpt-5.6-terra",
            "current_evidence": task_result,
            "attempts": [
                {
                    "attempt": 1,
                    "validity": "VALID",
                    "assigned_model": "gpt-5.6-terra",
                    "actual_model": "gpt-5.6-terra",
                    "agent_id": "worker-1",
                    "input_state_id": source_baseline["state_id"],
                    "output_state_id": post_workspace["state_id"],
                    "workspace_root": str(disposable),
                    "workspace_id": post_workspace["workspace_id"],
                    "runtime_attestation": worker_attestation,
                    "contract_manifest": task_input,
                    "addresses_findings": [],
                    "evidence_manifest": task_result,
                }
            ],
        }
    )
    test = doc.entity("TEST-101")
    test.data.update(
        {
            "status": "PASS",
            "attempt": 1,
            "actual": "PASS",
            "evidence": test_result,
            "results": [
                {
                    "attempt": 1,
                    "validity": "VALID",
                    "task_refs": ["DEV-101"],
                    "tested_state_id": post_workspace["state_id"],
                    "command_sha256": test.data["command_sha256"],
                    "input_manifest": test_input,
                    "result": "PASS",
                    "evidence_manifest": test_result,
                }
            ],
        }
    )
    qa = doc.entity("QA-101")
    qa.data.update(
        {
            "status": "FINISHED",
            "verdict": "PASS",
            "current_attempt": 1,
            "attempts": [
                {
                    "attempt": 1,
                    "validity": "VALID",
                    "verdict": "PASS",
                    "agent_id": "qa-1",
                    "requested_model": "gpt-5.6-sol",
                    "actual_model": "gpt-5.6-sol",
                    "context_mode": "NONE",
                    "input_state_id": post_workspace["state_id"],
                    "workspace_root": str(disposable),
                    "workspace_id": post_workspace["workspace_id"],
                    "runtime_attestation": qa_attestation,
                    "input_manifest": qa_input,
                    "resolved_findings": [],
                    "evidence_manifest": qa_result,
                }
            ],
        }
    )
    plan.write_text(doc.render(), encoding="utf-8")
    expected_sha = text_sha256(plan.read_text(encoding="utf-8"))

    output_manifest = evidence_dir / "P1" / "integrated.json"
    rollback_dir = evidence_dir / "P1" / "rollback"
    integrated, _ = integrate_workspace(
        source_root=root,
        workspace_root=disposable,
        source_baseline=source_baseline,
        workspace_baseline=disposable_baseline,
        allowed_paths=["scripts/**"],
        allowed_new_paths=["scripts/**"],
        output_manifest=output_manifest,
        rollback_dir=rollback_dir,
        plan_file=plan,
        plan_id=plan_id,
        phase_id="P1",
        expected_plan_sha256=expected_sha,
        expected_document_version=7,
    )
    assert integrated["state_id"] == post_workspace["state_id"]

    updated, _ = apply_event_atomic(
        plan,
        {
            "event": "PHASE_APPROVED",
            "payload": {
                "phase_id": "P1",
                "input_state_id": post_workspace["state_id"],
                "approval_evidence": approval_ref,
                "integration_manifest": _ref(root, output_manifest),
                "integration_journal": _ref(root, rollback_dir / "journal.json"),
            },
        },
        expected_sha256=expected_sha,
        expected_document_version=7,
    )
    assert updated.metadata["status"] == "QA"
    assert updated.entity("P1").data["status"] == "DONE"
    assert (root / "scripts" / "product.txt").read_text(encoding="utf-8") == "after\n"
    marker = json.loads((rollback_dir / "COMMITTED.json").read_text(encoding="utf-8"))
    assert marker["status"] == "COMMITTED"

    final_dir = evidence_dir / "QA-FINAL" / "attempt-0001"
    final_contract = final_dir / "qa-contract.yaml"
    _write(final_contract, "contract_version: codex-qa-contract/v1\n")
    final_disposable = tmp_path / "final-qa"
    final_disposable_baseline_path = tmp_path / "final-qa-baseline.json"
    final_workspace = prepare_copy(
        root,
        final_disposable,
        final_disposable_baseline_path,
    )
    assert final_workspace["state_id"] == post_workspace["state_id"]
    final_workspace_path = final_dir / "workspace.json"
    _write_json(final_workspace_path, final_workspace)
    final_input = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="QA-FINAL",
        attempt=1,
        stage="INPUT",
        input_state_id=post_workspace["state_id"],
        output_state_id=None,
        input_manifest=None,
        role_files={
            "qa_contract": final_contract,
            "workspace_manifest": final_workspace_path,
        },
    )
    final_attestation = _attestation(
        root,
        final_dir / "runtime-attestation.json",
        agent_id="qa-final-1",
        role="QA",
        model="gpt-5.6-sol",
        workspace_root=str(final_disposable),
        workspace_id=final_workspace["workspace_id"],
    )
    current_text = plan.read_text(encoding="utf-8")
    with pytest.raises(Exception) as caught:
        apply_event_atomic(
            plan,
            {
                "event": "PLAN_QA_STARTED",
                "payload": {
                    "qa_id": "QA-FINAL",
                    "agent_id": "qa-final-1",
                    "requested_model": "gpt-5.6-sol",
                    "actual_model": "gpt-5.6-sol",
                    "context_mode": "NONE",
                    "input_state_id": post_workspace["state_id"],
                    "input_manifest": final_input,
                    "deadline": "2099-07-25T12:10:00+09:00",
                    "workspace_root": str(root),
                    "workspace_id": integrated["workspace_id"],
                    "runtime_attestation": final_attestation,
                },
            },
            expected_sha256=text_sha256(current_text),
            expected_document_version=8,
        )
    assert getattr(caught.value, "code", None) == "WORKSPACE_NOT_DISPOSABLE"
    assert text_sha256(plan.read_text(encoding="utf-8")) == text_sha256(current_text)

    started, _ = apply_event_atomic(
        plan,
        {
            "event": "PLAN_QA_STARTED",
            "payload": {
                "qa_id": "QA-FINAL",
                "agent_id": "qa-final-1",
                "requested_model": "gpt-5.6-sol",
                "actual_model": "gpt-5.6-sol",
                "context_mode": "NONE",
                "input_state_id": post_workspace["state_id"],
                "input_manifest": final_input,
                "deadline": "2099-07-25T12:10:00+09:00",
                "workspace_root": str(final_disposable),
                "workspace_id": final_workspace["workspace_id"],
                "runtime_attestation": final_attestation,
            },
        },
        expected_sha256=text_sha256(current_text),
        expected_document_version=8,
    )
    assert started.entity("QA-FINAL").data["status"] == "RUNNING"

    final_pre_state = final_dir / "pre-state.json"
    final_post_state = final_dir / "post-state.json"
    _write_json(final_pre_state, final_workspace)
    _write_json(final_post_state, final_workspace)
    final_artifacts = {
        "pre_state": final_pre_state,
        "post_state": final_post_state,
    }
    for role in ("qa_response", "qa_report"):
        artifact = final_dir / f"{role}.txt"
        _write(artifact, f"{role}: PASS\n")
        final_artifacts[role] = artifact
    final_result = _attempt_manifest(
        root=root,
        plan_id=plan_id,
        entity_id="QA-FINAL",
        attempt=1,
        stage="RESULT",
        input_state_id=post_workspace["state_id"],
        output_state_id=post_workspace["state_id"],
        input_manifest=final_input,
        role_files=final_artifacts,
    )
    current_text = plan.read_text(encoding="utf-8")
    reported, _ = apply_event_atomic(
        plan,
        {
            "event": "FINAL_QA_REPORTED",
            "payload": {
                "qa_id": "QA-FINAL",
                "verdict": "PASS",
                "resolved_findings": [],
                "findings": [],
                "evidence_manifest": final_result,
            },
        },
        expected_sha256=text_sha256(current_text),
        expected_document_version=9,
    )
    assert reported.entity("QA-FINAL").data["verdict"] == "PASS"

    final_approval = evidence_dir / "PLAN" / "approval.yaml"
    _write(
        final_approval,
        yaml.safe_dump(
            {
                "schema": "codex-approval-evidence/v1",
                "plan_id": plan_id,
                "approval_kind": "PLAN",
                "entity_id": plan_id,
                "approver_role": "LEAD",
                "decision": "APPROVED",
                "created_at": "2026-07-25T12:15:00+09:00",
                "statement": "최종 QA와 전체 evidence graph를 승인한다.",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    final_approval_ref = _ref(root, final_approval)
    approval_event = {
        "event": "PLAN_APPROVED",
        "payload": {
            "input_state_id": post_workspace["state_id"],
            "approval_evidence": final_approval_ref,
            "residual_risks": [],
        },
    }

    planning_path = root / planning_ref["path"]
    planning_bytes = planning_path.read_bytes()
    planning_path.write_bytes(planning_bytes + b"# tampered\n")
    current_text = plan.read_text(encoding="utf-8")
    try:
        apply_event_atomic(
            plan,
            approval_event,
            expected_sha256=text_sha256(current_text),
            expected_document_version=10,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) in {
            "EVIDENCE_HASH_MISMATCH",
            "EVIDENCE_SIZE_MISMATCH",
        }
    else:
        raise AssertionError("PLAN_APPROVED accepted a tampered planning baseline")
    assert parse_plan(plan).metadata["status"] == "QA"
    planning_path.write_bytes(planning_bytes)

    current_text = plan.read_text(encoding="utf-8")
    completed, _ = apply_event_atomic(
        plan,
        approval_event,
        expected_sha256=text_sha256(current_text),
        expected_document_version=10,
    )
    assert completed.metadata["status"] == "COMPLETED"
