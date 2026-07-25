from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.plan_core import (
    build_plan_content,
    evidence_ref,
    parse_plan,
    validate_executable,
    validate_structural,
)
from scripts.workspace_guard import DEFAULT_IGNORES, create_manifest


def make_plan(tmp_path: Path, complete_spec: dict) -> Path:
    plan_dir = tmp_path / "dev-plan"
    plan_dir.mkdir()
    path = plan_dir / "implement_20260725_120003.md"
    path.write_text(
        build_plan_content(
            filename=path.name,
            plan_id="PLAN-20260725-120003",
            created_at="2026-07-25T12:00:03+09:00",
            spec=complete_spec,
            lead_model="gpt-5.6-sol",
            qa_model="gpt-5.6-sol",
            isolation_mode="MANIFEST_GUARDED",
        ),
        encoding="utf-8",
    )
    return path


def test_ready_candidate_validates_without_mutating_plan(
    tmp_path: Path,
    complete_spec: dict,
    cli,
) -> None:
    plan = make_plan(tmp_path, complete_spec)
    evidence = tmp_path / "dev-plan" / "evidence" / "PLAN-20260725-120003" / "baseline" / "planning.txt"
    evidence.parent.mkdir(parents=True)
    workspace = evidence.parent / "workspace.json"
    workspace_manifest = create_manifest(tmp_path, list(DEFAULT_IGNORES))
    workspace.write_text(json.dumps(workspace_manifest, indent=2) + "\n", encoding="utf-8")
    workspace_ref = evidence_ref(
        "dev-plan/evidence/PLAN-20260725-120003/baseline/workspace.json",
        project_root=tmp_path,
    )
    evidence.write_text(
        yaml.safe_dump(
            {
                "manifest_version": "codex-evidence-manifest/v1",
                "plan_id": "PLAN-20260725-120003",
                "entity_id": "PLAN",
                "attempt": 0,
                "stage": "BASELINE",
                "created_at": "2026-07-25T12:00:03+09:00",
                "validity": "VALID",
                "output_state_id": workspace_manifest["state_id"],
                "files": [{"role": "workspace_manifest", **workspace_ref}],
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
                "dev-plan/evidence/PLAN-20260725-120003/baseline/planning.txt",
                project_root=tmp_path,
            ),
        },
    }
    event_path = evidence.parent / "ready.yaml"
    event_path.write_text(yaml.safe_dump(event, sort_keys=False), encoding="utf-8")
    before = plan.read_bytes()
    result = cli(
        "validate_dev_plan.py",
        plan,
        "--level",
        "executable",
        "--target-state",
        "READY",
        "--candidate-event",
        event_path,
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["valid"] is True
    assert plan.read_bytes() == before


def test_executable_rejects_path_and_command_tampering(
    tmp_path: Path,
    complete_spec: dict,
) -> None:
    plan = make_plan(tmp_path, complete_spec)
    doc = parse_plan(plan)
    doc.metadata["status"] = "READY"
    doc.metadata["planning_revision"] = "git:abc"
    doc.metadata["planning_evidence"] = {
        "path": "not-checked",
        "sha256": "0" * 64,
        "bytes": 0,
    }
    doc.entity("DEV-101").data["allowed_paths"] = ["../escape"]
    doc.entity("TEST-101").data["argv"].append("-q")
    errors = validate_executable(doc, check_evidence=False)
    codes = {error.code for error in errors}
    assert "PATH_INVALID" in codes
    assert "COMMAND_DIGEST_MISMATCH" in codes


def test_duplicate_yaml_key_is_rejected(tmp_path: Path, complete_spec: dict) -> None:
    plan = make_plan(tmp_path, complete_spec)
    text = plan.read_text(encoding="utf-8").replace(
        "status: DRAFT\ncurrent_phase:",
        "status: DRAFT\nstatus: READY\ncurrent_phase:",
        1,
    )
    plan.write_text(text, encoding="utf-8")
    try:
        parse_plan(plan)
    except Exception as exc:
        assert getattr(exc, "code", None) == "YAML_DUPLICATE_KEY"
    else:
        raise AssertionError("duplicate YAML key was accepted")


def test_structural_detects_checkbox_mismatch(tmp_path: Path, complete_spec: dict) -> None:
    plan = make_plan(tmp_path, complete_spec)
    text = plan.read_text(encoding="utf-8").replace("- [ ] 완료", "- [x] 완료", 1)
    plan.write_text(text, encoding="utf-8")
    codes = {error.code for error in validate_structural(parse_plan(plan))}
    assert "CHECKBOX_STATE_MISMATCH" in codes
