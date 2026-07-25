from __future__ import annotations

import json
import socket
from pathlib import Path

from scripts.plan_core import (
    apply_event_atomic,
    build_plan_content,
    evidence_ref,
    parse_plan,
    text_sha256,
)
from scripts.workspace_guard import DEFAULT_IGNORES, create_manifest


def mark_phase_qa_ready(plan: Path, aggregate_state_id: str) -> str:
    worker_ref = {
        "path": "dev-plan/evidence/test/worker.yaml",
        "sha256": "a" * 64,
        "bytes": 1,
    }
    test_ref = {
        "path": "dev-plan/evidence/test/test.yaml",
        "sha256": "c" * 64,
        "bytes": 1,
    }
    qa_ref = {
        "path": "dev-plan/evidence/test/qa.yaml",
        "sha256": "b" * 64,
        "bytes": 1,
    }
    doc = parse_plan(plan)
    doc.metadata["status"] = "IN_PROGRESS"
    doc.metadata["current_phase"] = "P1"
    phase = doc.entity("P1")
    phase.data["status"] = "QA"
    for task in [item for item in doc.blocks_of("task") if item.phase_id == "P1"]:
        task.data["status"] = "WORKER_DONE"
        task.data["attempt"] = 1
        task.data["worker_tier"] = "TERRA"
        task.data["assigned_model"] = "gpt-5.6-terra"
        task.data["current_evidence"] = worker_ref
        task.data["attempts"] = [
            {
                "attempt": 1,
                "validity": "VALID",
                "assigned_model": "gpt-5.6-terra",
                "actual_model": "gpt-5.6-terra",
                "input_state_id": "pre-integration-state",
                "output_state_id": aggregate_state_id,
                "evidence_manifest": worker_ref,
            }
        ]
    for test in [item for item in doc.blocks_of("test") if item.phase_id == "P1"]:
        test.data["status"] = "PASS"
        test.data["attempt"] = 1
        test.data["actual"] = "PASS"
        test.data["evidence"] = test_ref
        test.data["results"] = [
            {
                "attempt": 1,
                "validity": "VALID",
                "tested_state_id": aggregate_state_id,
                "result": "PASS",
                "evidence_manifest": test_ref,
            }
        ]
    qa = next(item for item in doc.blocks_of("qa") if item.phase_id == "P1")
    qa.data["status"] = "FINISHED"
    qa.data["verdict"] = "PASS"
    qa.data["current_attempt"] = 1
    qa.data["attempts"] = [
        {
            "attempt": 1,
            "validity": "VALID",
            "verdict": "PASS",
            "agent_id": "qa-test",
            "requested_model": "gpt-5.6-sol",
            "actual_model": "gpt-5.6-sol",
            "context_mode": "NONE",
            "input_state_id": aggregate_state_id,
            "evidence_manifest": qa_ref,
        }
    ]
    plan.write_text(doc.render(), encoding="utf-8")
    return text_sha256(plan.read_text(encoding="utf-8"))


def test_workspace_guard_detects_and_allows_scoped_changes(tmp_path: Path, cli) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "allowed.txt").write_text("one\n", encoding="utf-8")
    (workspace / "protected.txt").write_text("safe\n", encoding="utf-8")
    manifest = tmp_path / "baseline.json"
    snapshot = cli(
        "workspace_guard.py",
        "snapshot",
        "--root",
        workspace,
        "--output",
        manifest,
        "--format",
        "json",
    )
    assert snapshot.returncode == 0, snapshot.stderr
    assert json.loads(snapshot.stdout)["state_id"].startswith("sha256:")

    (workspace / "src" / "allowed.txt").write_text("two\n", encoding="utf-8")
    (workspace / "protected.txt").write_text("changed\n", encoding="utf-8")
    rejected = cli(
        "workspace_guard.py",
        "verify",
        manifest,
        "--allowed-path",
        "src/**",
        "--format",
        "json",
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["violations"] == [
        {"path": "protected.txt", "change": "MODIFIED"}
    ]

    accepted = cli(
        "workspace_guard.py",
        "verify",
        manifest,
        "--allowed-path",
        "src/**",
        "--allowed-path",
        "protected.txt",
    )
    assert accepted.returncode == 0


def test_workspace_guard_rejects_escaping_file_and_directory_symlinks(tmp_path: Path, cli) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.txt"
    workspace.mkdir()
    outside.write_text("outside\n", encoding="utf-8")
    (workspace / "escape").symlink_to(outside)
    result = cli(
        "workspace_guard.py",
        "snapshot",
        "--root",
        workspace,
        "--output",
        tmp_path / "manifest.json",
    )
    assert result.returncode == 2
    assert "escapes workspace root" in result.stderr

    (workspace / "escape").unlink()
    outside_directory = tmp_path / "outside-directory"
    outside_directory.mkdir()
    (outside_directory / "secret.txt").write_text("secret\n", encoding="utf-8")
    (workspace / "escape-directory").symlink_to(outside_directory, target_is_directory=True)
    directory_result = cli(
        "workspace_guard.py",
        "snapshot",
        "--root",
        workspace,
        "--output",
        tmp_path / "directory-manifest.json",
        "--no-default-ignores",
    )
    assert directory_result.returncode == 2
    assert "escapes workspace root" in directory_result.stderr


def test_prepare_copy_and_integrate_use_source_preimage_cas(
    tmp_path: Path,
    cli,
    complete_spec: dict,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "item.txt").write_text("one\n", encoding="utf-8")
    (source / "protected.txt").write_text("safe\n", encoding="utf-8")
    plan = source / "dev-plan" / "implement_20260725_120099.md"
    plan.parent.mkdir()
    spec = json.loads(json.dumps(complete_spec))
    task_spec = spec["phases"][0]["tasks"][0]
    task_spec["allowed_paths"] = ["src/**"]
    task_spec["allowed_new_paths"] = ["src/**"]
    task_spec["read_paths"] = ["src/**"]
    plan_content = build_plan_content(
        filename=plan.name,
        plan_id="PLAN-20260725-120099",
        created_at="2026-07-25T12:00:00+09:00",
        spec=spec,
        lead_model="gpt-5.6-sol",
        qa_model="gpt-5.6-sol",
        isolation_mode="MANIFEST_GUARDED",
    )
    plan.write_text(plan_content, encoding="utf-8")
    source_baseline = tmp_path / "source-baseline.json"
    assert (
        cli(
            "workspace_guard.py",
            "snapshot",
            "--root",
            source,
            "--output",
            source_baseline,
        ).returncode
        == 0
    )

    workspace = tmp_path / "attempt-workspace"
    workspace_baseline = tmp_path / "workspace-baseline.json"
    prepared = cli(
        "workspace_guard.py",
        "prepare-copy",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--baseline-manifest",
        workspace_baseline,
    )
    assert prepared.returncode == 0, prepared.stderr
    (workspace / "src" / "item.txt").write_text("two\n", encoding="utf-8")
    (workspace / "src" / "new.txt").write_text("new\n", encoding="utf-8")
    pre_qa = cli(
        "workspace_guard.py",
        "integrate",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--source-baseline",
        source_baseline,
        "--workspace-baseline",
        workspace_baseline,
        "--output-manifest",
        source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "pre-qa" / "integrated.json",
        "--rollback-dir",
        source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "pre-qa" / "rollback",
        "--plan-file",
        plan,
        "--plan-id",
        "PLAN-20260725-120099",
        "--phase-id",
        "P1",
        "--expected-plan-sha256",
        text_sha256(plan.read_text(encoding="utf-8")),
        "--expected-document-version",
        "0",
        "--allowed-path",
        "src/**",
        "--allowed-new-path",
        "src/**",
    )
    assert pre_qa.returncode == 2
    assert "not ready for post-QA integration" in pre_qa.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "one\n"

    plan_sha = mark_phase_qa_ready(
        plan,
        create_manifest(workspace, list(DEFAULT_IGNORES))["state_id"],
    )
    widened = cli(
        "workspace_guard.py",
        "integrate",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--source-baseline",
        source_baseline,
        "--workspace-baseline",
        workspace_baseline,
        "--output-manifest",
        source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "attempt-0" / "integrated.json",
        "--rollback-dir",
        source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "attempt-0" / "rollback",
        "--plan-file",
        plan,
        "--plan-id",
        "PLAN-20260725-120099",
        "--phase-id",
        "P1",
        "--expected-plan-sha256",
        plan_sha,
        "--expected-document-version",
        "0",
        "--allowed-path",
        "src/**",
        "--allowed-path",
        "protected.txt",
        "--allowed-new-path",
        "src/**",
    )
    assert widened.returncode == 2
    assert "allowlist differs" in widened.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "one\n"

    output_manifest = source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "attempt-1" / "integrated.json"
    rollback_dir = source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "attempt-1" / "rollback"
    integrated = cli(
        "workspace_guard.py",
        "integrate",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--source-baseline",
        source_baseline,
        "--workspace-baseline",
        workspace_baseline,
        "--output-manifest",
        output_manifest,
        "--rollback-dir",
        rollback_dir,
        "--plan-file",
        plan,
        "--plan-id",
        "PLAN-20260725-120099",
        "--phase-id",
        "P1",
        "--expected-plan-sha256",
        plan_sha,
        "--expected-document-version",
        "0",
        "--allowed-path",
        "src/**",
        "--allowed-new-path",
        "src/**",
    )
    assert integrated.returncode == 0, integrated.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "two\n"
    assert (source / "src" / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert (source / "protected.txt").read_text(encoding="utf-8") == "safe\n"
    journal_ref = evidence_ref(
        str((rollback_dir / "journal.json").relative_to(source)),
        project_root=source,
    )
    plan.write_text("# changed after integration\n", encoding="utf-8")
    try:
        apply_event_atomic(
            plan,
            {
                "event": "PHASE_APPROVED",
                "payload": {
                    "phase_id": "P1",
                    "integration_journal": journal_ref,
                },
            },
            expected_sha256=plan_sha,
            expected_document_version=0,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "PLAN_EVENT_ROLLED_BACK"
    else:
        raise AssertionError("stale Plan CAS did not trigger integration rollback")
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "one\n"
    assert not (source / "src" / "new.txt").exists()
    plan.write_text(plan_content, encoding="utf-8")

    second_workspace = tmp_path / "attempt-workspace-2"
    second_baseline = tmp_path / "workspace-baseline-2.json"
    source_baseline_2 = tmp_path / "source-baseline-2.json"
    assert (
        cli(
            "workspace_guard.py",
            "snapshot",
            "--root",
            source,
            "--output",
            source_baseline_2,
        ).returncode
        == 0
    )
    assert (
        cli(
            "workspace_guard.py",
            "prepare-copy",
            "--source-root",
            source,
            "--workspace-root",
            second_workspace,
            "--baseline-manifest",
            second_baseline,
        ).returncode
        == 0
    )
    (second_workspace / "src" / "item.txt").write_text("three\n", encoding="utf-8")
    (source / "protected.txt").write_text("user-change\n", encoding="utf-8")
    second_plan_sha = mark_phase_qa_ready(
        plan,
        create_manifest(second_workspace, list(DEFAULT_IGNORES))["state_id"],
    )
    rejected = cli(
        "workspace_guard.py",
        "integrate",
        "--source-root",
        source,
        "--workspace-root",
        second_workspace,
        "--source-baseline",
        source_baseline_2,
        "--workspace-baseline",
        second_baseline,
        "--output-manifest",
        source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "attempt-2" / "integrated.json",
        "--rollback-dir",
        source / "dev-plan" / "evidence" / "PLAN-20260725-120099" / "attempt-2" / "rollback",
        "--plan-file",
        plan,
        "--plan-id",
        "PLAN-20260725-120099",
        "--phase-id",
        "P1",
        "--expected-plan-sha256",
        second_plan_sha,
        "--expected-document-version",
        "0",
        "--allowed-path",
        "src/**",
        "--allowed-new-path",
        "src/**",
    )
    assert rejected.returncode == 2
    assert "preimage changed" in rejected.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "one\n"


def test_prepared_rollback_rejects_user_changes_and_recovers_partial_apply(
    tmp_path: Path,
    cli,
    complete_spec: dict,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "item.txt").write_text("one\n", encoding="utf-8")
    plan = source / "dev-plan" / "implement_20260725_120100.md"
    plan.parent.mkdir()
    spec = json.loads(json.dumps(complete_spec))
    task_spec = spec["phases"][0]["tasks"][0]
    task_spec["allowed_paths"] = ["src/**"]
    task_spec["allowed_new_paths"] = ["src/**"]
    task_spec["read_paths"] = ["src/**"]
    plan.write_text(
        build_plan_content(
            filename=plan.name,
            plan_id="PLAN-20260725-120100",
            created_at="2026-07-25T12:01:00+09:00",
            spec=spec,
            lead_model="gpt-5.6-sol",
            qa_model="gpt-5.6-sol",
            isolation_mode="MANIFEST_GUARDED",
        ),
        encoding="utf-8",
    )
    source_baseline = tmp_path / "source-baseline.json"
    assert cli(
        "workspace_guard.py",
        "snapshot",
        "--root",
        source,
        "--output",
        source_baseline,
    ).returncode == 0
    workspace = tmp_path / "workspace"
    workspace_baseline = tmp_path / "workspace-baseline.json"
    assert cli(
        "workspace_guard.py",
        "prepare-copy",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--baseline-manifest",
        workspace_baseline,
    ).returncode == 0
    (workspace / "src" / "item.txt").write_text("two\n", encoding="utf-8")
    (workspace / "src" / "new.txt").write_text("new\n", encoding="utf-8")
    plan_sha = mark_phase_qa_ready(
        plan,
        create_manifest(workspace, list(DEFAULT_IGNORES))["state_id"],
    )
    evidence = source / "dev-plan" / "evidence" / "PLAN-20260725-120100" / "attempt"
    rollback_dir = evidence / "rollback"
    assert cli(
        "workspace_guard.py",
        "integrate",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--source-baseline",
        source_baseline,
        "--workspace-baseline",
        workspace_baseline,
        "--output-manifest",
        evidence / "integrated.json",
        "--rollback-dir",
        rollback_dir,
        "--plan-file",
        plan,
        "--plan-id",
        "PLAN-20260725-120100",
        "--phase-id",
        "P1",
        "--expected-plan-sha256",
        plan_sha,
        "--expected-document-version",
        "0",
        "--allowed-path",
        "src/**",
        "--allowed-new-path",
        "src/**",
    ).returncode == 0

    journal_path = rollback_dir / "journal.json"
    commit_marker = rollback_dir / "COMMITTED.json"
    commit_marker.write_text(
        json.dumps(
            {
                "schema": "codex-integration-commit/v1",
                "status": "COMMITTED",
            }
        ),
        encoding="utf-8",
    )
    replay = cli(
        "workspace_guard.py",
        "rollback",
        "--journal",
        journal_path,
    )
    assert replay.returncode == 2
    assert "no longer rollbackable" in replay.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "two\n"
    commit_marker.unlink()

    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["status"] = "PREPARED"
    journal["post_state_id"] = "NONE"
    journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
    (source / ".codex-dev-plan-integration.lock").write_text(
        json.dumps(
            {
                "pid": 99_999_999,
                "host": socket.gethostname(),
                "created_at": "2026-07-25T12:00:00+09:00",
            }
        ),
        encoding="utf-8",
    )

    (source / "src" / "item.txt").write_text("user-change\n", encoding="utf-8")
    rejected = cli(
        "workspace_guard.py",
        "rollback",
        "--journal",
        journal_path,
    )
    assert rejected.returncode == 2
    assert "rollback CAS rejected" in rejected.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "user-change\n"

    # Simulate a crash after one path was still at its preimage and another was applied.
    (source / "src" / "item.txt").write_text("one\n", encoding="utf-8")
    recovered = cli(
        "workspace_guard.py",
        "rollback",
        "--journal",
        journal_path,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert (source / "src" / "item.txt").read_text(encoding="utf-8") == "one\n"
    assert not (source / "src" / "new.txt").exists()


def test_failed_compensation_marks_valid_plan_blocked(
    tmp_path: Path,
    complete_spec: dict,
    cli,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "scripts").mkdir()
    (source / "scripts" / "item.txt").write_text("before\n", encoding="utf-8")
    plan = source / "dev-plan" / "implement_20260725_120300.md"
    plan.parent.mkdir()
    plan.write_text(
        build_plan_content(
            filename=plan.name,
            plan_id="PLAN-20260725-120300",
            created_at="2026-07-25T12:03:00+09:00",
            spec=complete_spec,
            lead_model="gpt-5.6-sol",
            qa_model="gpt-5.6-sol",
            isolation_mode="MANIFEST_GUARDED",
        ),
        encoding="utf-8",
    )
    source_baseline = tmp_path / "source-baseline.json"
    assert cli(
        "workspace_guard.py",
        "snapshot",
        "--root",
        source,
        "--output",
        source_baseline,
    ).returncode == 0
    workspace = tmp_path / "workspace"
    workspace_baseline = tmp_path / "workspace-baseline.json"
    assert cli(
        "workspace_guard.py",
        "prepare-copy",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--baseline-manifest",
        workspace_baseline,
    ).returncode == 0
    (workspace / "scripts" / "item.txt").write_text("integrated\n", encoding="utf-8")
    plan_sha = mark_phase_qa_ready(
        plan,
        create_manifest(workspace, list(DEFAULT_IGNORES))["state_id"],
    )
    evidence = source / "dev-plan" / "evidence" / "PLAN-20260725-120300" / "P1"
    rollback_dir = evidence / "rollback"
    assert cli(
        "workspace_guard.py",
        "integrate",
        "--source-root",
        source,
        "--workspace-root",
        workspace,
        "--source-baseline",
        source_baseline,
        "--workspace-baseline",
        workspace_baseline,
        "--output-manifest",
        evidence / "integrated.json",
        "--rollback-dir",
        rollback_dir,
        "--plan-file",
        plan,
        "--plan-id",
        "PLAN-20260725-120300",
        "--phase-id",
        "P1",
        "--expected-plan-sha256",
        plan_sha,
        "--expected-document-version",
        "0",
        "--allowed-path",
        "scripts/**",
        "--allowed-new-path",
        "scripts/**",
    ).returncode == 0

    # A user change makes source rollback unsafe; a concurrent Plan edit makes
    # PHASE_APPROVED fail its original CAS.
    (source / "scripts" / "item.txt").write_text("user-change\n", encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    journal_ref = evidence_ref(
        str((rollback_dir / "journal.json").relative_to(source)),
        project_root=source,
    )
    try:
        apply_event_atomic(
            plan,
            {
                "event": "PHASE_APPROVED",
                "payload": {
                    "phase_id": "P1",
                    "integration_journal": journal_ref,
                },
            },
            expected_sha256=plan_sha,
            expected_document_version=0,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "INTEGRATION_ROLLBACK_FAILED"
        assert "Plan was marked BLOCKED" in str(exc)
    else:
        raise AssertionError("unsafe rollback did not fail closed")
    assert parse_plan(plan).metadata["status"] == "BLOCKED"
    assert (source / "scripts" / "item.txt").read_text(encoding="utf-8") == "user-change\n"
