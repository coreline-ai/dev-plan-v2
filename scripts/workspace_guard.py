#!/usr/bin/env python3
"""Create and verify deterministic workspace manifests for MANIFEST_GUARDED runs."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised by runtime preflight on non-POSIX hosts
    fcntl = None  # type: ignore[assignment]


SCHEMA = "codex-workspace-manifest/v1"
DEFAULT_IGNORES = [
    ".git/**",
    "dev-plan/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".codex-dev-plan-integration.lock",
]
PATH_RE = re.compile(r"^(?:[^/*?{}\[\]\\\x00]+/)*(?:[^/*?{}\[\]\\\x00]+|[^/*?{}\[\]\\\x00]+/\*\*)$")


class GuardError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MANIFEST_GUARDED workspace snapshot/verification")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="현재 workspace manifest 생성")
    snapshot.add_argument("--root", default=".")
    snapshot.add_argument("--output", required=True)
    snapshot.add_argument("--ignore", action="append", default=[])
    snapshot.add_argument("--no-default-ignores", action="store_true")
    snapshot.add_argument("--format", choices=["text", "json"], default="text")

    verify = subparsers.add_parser("verify", help="baseline과 현재 workspace 비교")
    verify.add_argument("manifest")
    verify.add_argument("--root")
    verify.add_argument("--allowed-path", action="append", default=[])
    verify.add_argument("--allowed-new-path", action="append", default=[])
    verify.add_argument("--format", choices=["text", "json"], default="text")

    prepare = subparsers.add_parser("prepare-copy", help="원본을 건드리지 않는 disposable copy 생성")
    prepare.add_argument("--source-root", required=True)
    prepare.add_argument("--workspace-root", required=True)
    prepare.add_argument("--baseline-manifest", required=True)
    prepare.add_argument("--format", choices=["text", "json"], default="text")

    integrate = subparsers.add_parser("integrate", help="preimage CAS 뒤 허용 변경만 원본에 통합")
    integrate.add_argument("--source-root", required=True)
    integrate.add_argument("--workspace-root", required=True)
    integrate.add_argument("--source-baseline", required=True)
    integrate.add_argument("--workspace-baseline", required=True)
    integrate.add_argument("--output-manifest", required=True)
    integrate.add_argument("--rollback-dir", required=True)
    integrate.add_argument("--plan-file", required=True)
    integrate.add_argument("--plan-id", required=True)
    integrate.add_argument("--phase-id", required=True)
    integrate.add_argument("--expected-plan-sha256", required=True)
    integrate.add_argument("--expected-document-version", required=True, type=int)
    integrate.add_argument("--allowed-path", action="append", default=[])
    integrate.add_argument("--allowed-new-path", action="append", default=[])
    integrate.add_argument("--format", choices=["text", "json"], default="text")

    rollback = subparsers.add_parser("rollback", help="plan 상태 갱신 실패 후 통합 원복")
    rollback.add_argument("--journal", required=True)
    rollback.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def valid_pattern(value: str, *, allow_control: bool = False) -> bool:
    if not isinstance(value, str) or not PATH_RE.fullmatch(value):
        return False
    if value in {".", "**"} or value.startswith("/") or "\\" in value:
        return False
    if any(part in {".", ".."} for part in value.split("/")):
        return False
    if not allow_control and (
        value in {".git/**", "dev-plan/**"}
        or value.startswith(".git/")
        or value.startswith("dev-plan/")
    ):
        return False
    return True


def matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern


def ignored(path: str, patterns: list[str]) -> bool:
    return any(matches(path, pattern) for pattern in patterns)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root: Path, ignore_patterns: list[str]) -> list[dict[str, Any]]:
    root = root.resolve()
    if not root.is_dir():
        raise GuardError(f"Workspace root is not a directory: {root}")
    files: list[dict[str, Any]] = []
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(root).as_posix()
        retained_directories: list[str] = []
        for name in sorted(names):
            relative = name if relative_directory == "." else f"{relative_directory}/{name}"
            if ignored(relative, ignore_patterns):
                continue
            path = directory_path / name
            if path.is_symlink():
                target = os.readlink(path)
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    raise GuardError(f"Symlink escapes workspace root: {relative} -> {target}")
                files.append(
                    {
                        "path": relative,
                        "type": "symlink",
                        "target": target,
                        "mode": stat.S_IMODE(path.lstat().st_mode),
                    }
                )
                continue
            retained_directories.append(name)
        names[:] = retained_directories
        for name in sorted(filenames):
            path = directory_path / name
            relative = path.relative_to(root).as_posix()
            if ignored(relative, ignore_patterns):
                continue
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                target = os.readlink(path)
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    raise GuardError(f"Symlink escapes workspace root: {relative} -> {target}")
                files.append(
                    {
                        "path": relative,
                        "type": "symlink",
                        "target": target,
                        "mode": stat.S_IMODE(metadata.st_mode),
                    }
                )
            elif stat.S_ISREG(metadata.st_mode):
                files.append(
                    {
                        "path": relative,
                        "type": "file",
                        "sha256": file_sha256(path),
                        "bytes": metadata.st_size,
                        "mode": stat.S_IMODE(metadata.st_mode),
                    }
                )
            else:
                raise GuardError(f"Unsupported filesystem entry: {relative}")
    return files


def state_id(files: list[dict[str, Any]]) -> str:
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_manifest(root: Path, ignore_patterns: list[str]) -> dict[str, Any]:
    files = collect(root, ignore_patterns)
    return {
        "schema": SCHEMA,
        "workspace_root": str(root.resolve()),
        "workspace_id": hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:24],
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "ignore": ignore_patterns,
        "state_id": state_id(files),
        "files": files,
    }


def write_manifest_exclusive(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise GuardError(f"Manifest already exists: {path}") from exc
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def update_json_atomic(path: Path, value: dict[str, Any]) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_copy(source: Path, workspace: Path, baseline_path: Path) -> dict[str, Any]:
    source = source.resolve()
    workspace = workspace.expanduser().absolute()
    if not source.is_dir():
        raise GuardError(f"Source root is not a directory: {source}")
    if workspace.exists() or workspace.is_symlink():
        raise GuardError(f"Workspace destination already exists: {workspace}")
    if workspace.resolve().is_relative_to(source):
        raise GuardError("Disposable workspace may not be created inside the source root")

    def ignore_callback(directory: str, names: list[str]) -> set[str]:
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(source).as_posix()
        return {
            name
            for name in names
            if ignored(
                name if relative_directory == "." else f"{relative_directory}/{name}",
                list(DEFAULT_IGNORES),
            )
        }

    try:
        shutil.copytree(
            source,
            workspace,
            symlinks=True,
            ignore=ignore_callback,
            copy_function=shutil.copy2,
        )
        manifest = create_manifest(workspace, list(DEFAULT_IGNORES))
        write_manifest_exclusive(baseline_path, manifest)
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    return manifest


class IntegrationLock:
    def __init__(self, source_root: Path, *, lock_name: str = ".codex-dev-plan-integration.lock"):
        self.path = source_root / lock_name
        self.acquired = False
        self.token = secrets.token_hex(16)
        self.identity: tuple[int, int] | None = None
        self.descriptor: int | None = None

    def __enter__(self) -> "IntegrationLock":
        if fcntl is None:
            raise GuardError("POSIX fcntl.flock support is required for integration locking")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise GuardError(f"Integration lock is held: {self.path}") from exc
        try:
            descriptor_stat = os.fstat(descriptor)
            path_stat = self.path.lstat()
            self.identity = (descriptor_stat.st_dev, descriptor_stat.st_ino)
            if self.identity != (path_stat.st_dev, path_stat.st_ino):
                raise GuardError(f"Integration lock path changed while acquiring: {self.path}")
            payload = json.dumps(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "created_at": dt.datetime.now().astimezone().isoformat(),
                    "token": self.token,
                    "state": "HELD",
                },
                sort_keys=True,
            ).encode("utf-8")
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
            _fsync_directory(self.path.parent)
        except Exception:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        self.acquired = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        descriptor = self.descriptor
        self.descriptor = None
        self.acquired = False
        if descriptor is None:
            return
        try:
            released_payload = json.dumps(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "released_at": dt.datetime.now().astimezone().isoformat(),
                    "token": self.token,
                    "state": "RELEASED",
                },
                sort_keys=True,
            ).encode("utf-8")
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            offset = 0
            while offset < len(released_payload):
                offset += os.write(descriptor, released_payload[offset:])
            os.fsync(descriptor)
        finally:
            assert fcntl is not None
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        raise GuardError(f"Refusing to replace a directory: {path}")


def _atomic_copy_file(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temp_path = Path(temp_name)
    try:
        with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)


def _phase_path_contract(
    plan_file: Path,
    *,
    plan_id: str,
    phase_id: str,
) -> tuple[list[str], list[str], str, int, str]:
    # Local import avoids a module-initialization cycle: plan_core imports this
    # module for manifest operations, while integration needs the canonical Plan
    # parser only when an integration command actually runs.
    try:
        from .plan_core import parse_plan
    except ImportError:
        from plan_core import parse_plan  # type: ignore

    try:
        plan = parse_plan(plan_file)
    except Exception as exc:
        raise GuardError(f"Bound Plan cannot be parsed: {exc}") from exc
    if plan.metadata.get("plan_id") != plan_id:
        raise GuardError("Integration plan_id differs from the bound Plan")
    phase = plan.entity(phase_id)
    if phase.kind != "phase":
        raise GuardError("Integration phase_id does not identify a Phase")
    tasks = [item for item in plan.blocks_of("task") if item.phase_id == phase_id]
    tests = [item for item in plan.blocks_of("test") if item.phase_id == phase_id]
    qa = next(
        (item for item in plan.blocks_of("qa") if item.phase_id == phase_id),
        None,
    )
    if (
        plan.metadata.get("status") != "IN_PROGRESS"
        or plan.metadata.get("current_phase") != phase_id
        or phase.data.get("status") != "QA"
        or not tasks
        or any(task.data.get("status") != "WORKER_DONE" for task in tasks)
        or any(test.data.get("status") != "PASS" for test in tests)
        or qa is None
        or qa.data.get("status") != "FINISHED"
        or qa.data.get("verdict") != "PASS"
    ):
        raise GuardError("Bound Phase is not ready for post-QA integration")
    qa_attempt_number = qa.data.get("current_attempt")
    qa_attempt = next(
        (
            item
            for item in reversed(qa.data.get("attempts", []) or [])
            if item.get("attempt") == qa_attempt_number
        ),
        None,
    )
    if (
        not isinstance(qa_attempt, dict)
        or qa_attempt.get("validity") != "VALID"
        or qa_attempt.get("verdict") != "PASS"
        or not isinstance(qa_attempt.get("input_state_id"), str)
        or not qa_attempt["input_state_id"]
    ):
        raise GuardError("Bound Phase QA current attempt is not VALID/PASS")
    for task in tasks:
        attempt_number = task.data.get("attempt")
        attempt = next(
            (
                item
                for item in reversed(task.data.get("attempts", []) or [])
                if item.get("attempt") == attempt_number
            ),
            None,
        )
        if (
            not isinstance(attempt, dict)
            or attempt.get("validity") != "VALID"
            or not isinstance(attempt.get("output_state_id"), str)
            or not attempt["output_state_id"]
        ):
            raise GuardError(f"{task.entity_id} has no current VALID output")
    allowed_paths = sorted(
        {
            str(pattern)
            for task in tasks
            for pattern in (task.data.get("allowed_paths", []) or [])
        }
    )
    allowed_new_paths = sorted(
        {
            str(pattern)
            for task in tasks
            for pattern in (task.data.get("allowed_new_paths", []) or [])
        }
    )
    value = {
        "plan_id": plan_id,
        "phase_id": phase_id,
        "allowed_paths": allowed_paths,
        "allowed_new_paths": allowed_new_paths,
    }
    digest = hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    version = plan.metadata.get("document_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise GuardError("Bound Plan document_version is invalid")
    return allowed_paths, allowed_new_paths, digest, version, qa_attempt["input_state_id"]


def _bound_plan_lock(plan_file: Path, expected_sha256: str) -> Any:
    try:
        from .plan_core import PlanFileLock
    except ImportError:
        from plan_core import PlanFileLock  # type: ignore

    return PlanFileLock(
        plan_file.with_suffix(plan_file.suffix + ".lock"),
        expected_sha256=expected_sha256,
    )


def integrate_workspace(
    *,
    source_root: Path,
    workspace_root: Path,
    source_baseline: dict[str, Any],
    workspace_baseline: dict[str, Any],
    allowed_paths: list[str],
    allowed_new_paths: list[str],
    output_manifest: Path,
    rollback_dir: Path,
    plan_file: Path,
    plan_id: str,
    phase_id: str,
    expected_plan_sha256: str,
    expected_document_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_root = source_root.resolve()
    workspace_root = workspace_root.resolve()
    if Path(str(source_baseline.get("workspace_root"))).resolve() != source_root:
        raise GuardError("source-baseline workspace_root mismatch")
    if Path(str(workspace_baseline.get("workspace_root"))).resolve() != workspace_root:
        raise GuardError("workspace-baseline workspace_root mismatch")
    if source_baseline.get("state_id") != workspace_baseline.get("state_id"):
        raise GuardError("Source and disposable workspace baselines differ")
    evidence_root = (source_root / "dev-plan" / "evidence").resolve()
    plan_evidence_root = (evidence_root / plan_id).resolve()
    output_manifest = output_manifest.resolve()
    rollback_dir = rollback_dir.resolve()
    if not output_manifest.is_relative_to(plan_evidence_root):
        raise GuardError("output-manifest must be under source/dev-plan/evidence/<plan-id>/")
    if not rollback_dir.is_relative_to(plan_evidence_root):
        raise GuardError("rollback-dir must be under source/dev-plan/evidence/<plan-id>/")
    if rollback_dir.exists():
        raise GuardError(f"rollback-dir already exists: {rollback_dir}")
    plan_file = plan_file.resolve()
    if (
        not plan_file.is_relative_to(source_root / "dev-plan")
        or not plan_file.is_file()
        or not re.fullmatch(r"PLAN-[0-9]{8}-[0-9]{6}", plan_id)
        or not re.fullmatch(r"P[1-9][0-9]*", phase_id)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256)
        or expected_document_version < 0
    ):
        raise GuardError("Integration Plan binding is invalid")
    if file_sha256(plan_file) != expected_plan_sha256:
        raise GuardError("Plan preimage differs from expected-plan-sha256")
    (
        contract_allowed,
        contract_new,
        contract_sha256,
        contract_version,
        qa_input_state_id,
    ) = _phase_path_contract(
        plan_file,
        plan_id=plan_id,
        phase_id=phase_id,
    )
    if contract_version != expected_document_version:
        raise GuardError("Integration document_version differs from the bound Plan")
    if (
        sorted(set(allowed_paths)) != contract_allowed
        or sorted(set(allowed_new_paths)) != contract_new
    ):
        raise GuardError("Integration allowlist differs from the bound Phase path contract")
    plan_evidence_root.mkdir(parents=True, exist_ok=True)

    workspace_current = create_manifest(workspace_root, list(workspace_baseline["ignore"]))
    if workspace_current["state_id"] != qa_input_state_id:
        raise GuardError("Disposable aggregate state differs from the PASS Phase QA input state")
    comparison = compare(workspace_baseline, workspace_current, contract_allowed, contract_new)
    if not comparison["valid"]:
        raise GuardError(f"Workspace contains out-of-contract changes: {comparison['violations']}")

    changes = comparison["changes"]
    changed_paths = [*changes["added"], *changes["deleted"], *changes["modified"]]
    workspace_entries = {entry["path"]: entry for entry in workspace_current["files"]}
    for relative in [*changes["added"], *changes["modified"]]:
        if workspace_entries[relative].get("type") != "file":
            raise GuardError(f"Changed symlinks are not integratable: {relative}")

    with IntegrationLock(source_root), IntegrationLock(
        evidence_root / plan_id,
        lock_name=".control-plane.lock",
    ), _bound_plan_lock(plan_file, expected_plan_sha256):
        if file_sha256(plan_file) != expected_plan_sha256:
            raise GuardError("Plan changed while acquiring integration locks")
        (
            locked_allowed,
            locked_new,
            locked_contract_sha256,
            locked_contract_version,
            locked_qa_input_state_id,
        ) = _phase_path_contract(
            plan_file,
            plan_id=plan_id,
            phase_id=phase_id,
        )
        if (
            locked_allowed != contract_allowed
            or locked_new != contract_new
            or locked_contract_sha256 != contract_sha256
            or locked_contract_version != expected_document_version
            or locked_qa_input_state_id != qa_input_state_id
        ):
            raise GuardError("Bound Phase contract changed while acquiring integration locks")
        source_current = create_manifest(source_root, list(source_baseline["ignore"]))
        if source_current["state_id"] != source_baseline["state_id"]:
            raise GuardError("Source preimage changed; integration CAS rejected")

        backups: dict[str, dict[str, Any] | None] = {}
        rollback_dir.mkdir(parents=True)
        backup_root = rollback_dir / "backups"
        applied: list[str] = []
        try:
            for relative in changed_paths:
                destination = source_root / relative
                resolved_parent = destination.parent.resolve()
                if not resolved_parent.is_relative_to(source_root):
                    raise GuardError(f"Integration path escapes source root: {relative}")
                if _path_exists(destination):
                    metadata = destination.lstat()
                    if stat.S_ISREG(metadata.st_mode):
                        backup = backup_root / relative
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(destination, backup)
                        backups[relative] = {
                            "kind": "file",
                            "path": str(backup.relative_to(rollback_dir)),
                            "sha256": file_sha256(backup),
                            "bytes": backup.stat().st_size,
                        }
                    elif stat.S_ISLNK(metadata.st_mode):
                        backups[relative] = {
                            "kind": "symlink",
                            "target": os.readlink(destination),
                        }
                    else:
                        raise GuardError(f"Unsupported source entry: {relative}")
                else:
                    backups[relative] = None

            journal = {
                "schema": "codex-integration-journal/v1",
                "status": "PREPARED",
                "source_root": str(source_root),
                "plan_file": str(plan_file),
                "plan_id": plan_id,
                "phase_id": phase_id,
                "expected_plan_sha256": expected_plan_sha256,
                "expected_document_version": expected_document_version,
                "allowed_paths": contract_allowed,
                "allowed_new_paths": contract_new,
                "path_contract_sha256": contract_sha256,
                "ignore": list(source_baseline["ignore"]),
                "pre_state_id": source_baseline["state_id"],
                "expected_post_state_id": workspace_current["state_id"],
                "post_state_id": "NONE",
                "pre_files": source_baseline["files"],
                "post_files": workspace_current["files"],
                "changes": changes,
                "backups": backups,
                "output_manifest": str(output_manifest),
                "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            journal_path = rollback_dir / "journal.json"
            write_manifest_exclusive(journal_path, journal)

            for relative in changes["deleted"]:
                _remove_path(source_root / relative)
                applied.append(relative)
            for relative in [*changes["added"], *changes["modified"]]:
                entry = workspace_entries[relative]
                destination = source_root / relative
                if destination.is_symlink():
                    destination.unlink()
                _atomic_copy_file(workspace_root / relative, destination, int(entry["mode"]))
                applied.append(relative)

            integrated = create_manifest(source_root, list(source_baseline["ignore"]))
            if integrated["state_id"] != workspace_current["state_id"]:
                raise GuardError("Integrated source state differs from verified workspace state")
            write_manifest_exclusive(output_manifest, integrated)
            journal["status"] = "INTEGRATED"
            journal["post_state_id"] = integrated["state_id"]
            journal["integrated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            update_json_atomic(journal_path, journal)
        except Exception as exc:
            for relative in reversed(applied):
                destination = source_root / relative
                _remove_path(destination)
                backup = backups.get(relative)
                if backup is None:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                if backup["kind"] == "file":
                    shutil.copy2(rollback_dir / backup["path"], destination)
                else:
                    destination.symlink_to(backup["target"])
            output_manifest.unlink(missing_ok=True)
            journal_path = rollback_dir / "journal.json"
            if journal_path.exists():
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
                journal["status"] = "ROLLED_BACK_INTERNAL"
                journal["failure"] = str(exc)
                journal["rolled_back_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
                update_json_atomic(journal_path, journal)
            else:
                shutil.rmtree(rollback_dir, ignore_errors=True)
            raise GuardError(f"Integration failed and was rolled back: {exc}") from exc
    return integrated, comparison


def rollback_integration(journal_path: Path) -> dict[str, Any]:
    journal_path = journal_path.resolve()
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("schema") != "codex-integration-journal/v1":
        raise GuardError("Invalid integration journal schema")
    if journal.get("status") not in {"PREPARED", "INTEGRATED"}:
        raise GuardError(f"Integration journal is not rollbackable: {journal.get('status')}")
    source_root = Path(str(journal.get("source_root"))).resolve()
    evidence_root = (source_root / "dev-plan" / "evidence").resolve()
    if not journal_path.is_relative_to(evidence_root):
        raise GuardError("Integration journal must be under source/dev-plan/evidence/")
    rollback_dir = journal_path.parent
    commit_marker = rollback_dir / "COMMITTED.json"
    with IntegrationLock(source_root), IntegrationLock(
        evidence_root / str(journal.get("plan_id")),
        lock_name=".control-plane.lock",
    ):
        if commit_marker.exists():
            try:
                marker = json.loads(commit_marker.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise GuardError(f"Integration commit marker is unreadable: {exc}") from exc
            if marker.get("schema") != "codex-integration-commit/v1":
                raise GuardError("Integration commit marker schema is invalid")
            if marker.get("status") == "COMMITTED":
                raise GuardError("Integration is committed to the Plan and is no longer rollbackable")
            if marker.get("status") != "COMMITTING":
                raise GuardError("Integration commit marker status is invalid")
            plan_file = Path(str(journal.get("plan_file"))).resolve()
            if not plan_file.is_file():
                raise GuardError("Bound Plan file is missing during COMMITTING recovery")
            current_plan_sha = file_sha256(plan_file)
            if current_plan_sha == marker.get("post_plan_sha256"):
                marker["status"] = "COMMITTED"
                marker["committed_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
                update_json_atomic(commit_marker, marker)
                raise GuardError("Plan postimage is committed; integration rollback is forbidden")
            if current_plan_sha != marker.get("pre_plan_sha256"):
                raise GuardError("Bound Plan state is neither the preimage nor committed postimage")
            commit_marker.unlink()
        current = create_manifest(source_root, list(journal["ignore"]))
        if (
            journal.get("status") == "INTEGRATED"
            and current["state_id"] != journal.get("post_state_id")
        ):
            raise GuardError("Source postimage changed; rollback CAS rejected")
        if journal.get("status") == "PREPARED":
            pre_files = journal.get("pre_files")
            post_files = journal.get("post_files")
            if not isinstance(pre_files, list) or not isinstance(post_files, list):
                raise GuardError("PREPARED journal is missing pre/post file inventories")
            if state_id(pre_files) != journal.get("pre_state_id"):
                raise GuardError("PREPARED journal preimage inventory is invalid")
            if state_id(post_files) != journal.get("expected_post_state_id"):
                raise GuardError("PREPARED journal postimage inventory is invalid")
            before = {entry["path"]: entry for entry in pre_files}
            after = {entry["path"]: entry for entry in post_files}
            observed = {entry["path"]: entry for entry in current["files"]}
            changed = {
                *journal["changes"].get("added", []),
                *journal["changes"].get("deleted", []),
                *journal["changes"].get("modified", []),
            }
            for relative in sorted(set(before) | set(after) | set(observed)):
                current_entry = observed.get(relative)
                if relative in changed:
                    if current_entry not in (None, before.get(relative), after.get(relative)):
                        raise GuardError(
                            f"Source changed after PREPARED journal; rollback CAS rejected: {relative}"
                        )
                    if current_entry is None and before.get(relative) is not None and after.get(relative) is not None:
                        raise GuardError(
                            f"Source has an unrecorded deletion; rollback CAS rejected: {relative}"
                        )
                elif current_entry != before.get(relative):
                    raise GuardError(
                        f"Source changed outside the integration set; rollback CAS rejected: {relative}"
                    )
        backups = journal.get("backups")
        if not isinstance(backups, dict):
            raise GuardError("Integration journal backups are invalid")
        changed_paths = [
            *journal["changes"].get("added", []),
            *journal["changes"].get("deleted", []),
            *journal["changes"].get("modified", []),
        ]
        if current["state_id"] != journal.get("pre_state_id"):
            for relative in reversed(changed_paths):
                destination = source_root / relative
                _remove_path(destination)
                backup = backups.get(relative)
                if backup is None:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                if backup.get("kind") == "file":
                    backup_path = (rollback_dir / str(backup.get("path"))).resolve()
                    if not backup_path.is_relative_to(rollback_dir) or not backup_path.is_file():
                        raise GuardError(f"Rollback backup is missing: {relative}")
                    if (
                        file_sha256(backup_path) != backup.get("sha256")
                        or backup_path.stat().st_size != backup.get("bytes")
                    ):
                        raise GuardError(f"Rollback backup integrity failed: {relative}")
                    shutil.copy2(backup_path, destination)
                elif backup.get("kind") == "symlink":
                    destination.symlink_to(str(backup.get("target")))
                else:
                    raise GuardError(f"Rollback backup kind is invalid: {relative}")
        restored = create_manifest(source_root, list(journal["ignore"]))
        if restored["state_id"] != journal.get("pre_state_id"):
            raise GuardError("Rollback result differs from the recorded preimage")
        journal["status"] = "ROLLED_BACK"
        journal["rolled_back_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        output_path = Path(str(journal.get("output_manifest", ""))).resolve()
        if not output_path.is_relative_to(evidence_root):
            raise GuardError("Journal output_manifest escapes evidence root")
        output_path.unlink(missing_ok=True)
        update_json_atomic(journal_path, journal)
    return {
        "status": "INTEGRATION_ROLLED_BACK",
        "source_root": str(source_root),
        "state_id": restored["state_id"],
        "journal": str(journal_path),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise GuardError(f"Invalid workspace manifest: {path}")
    if not isinstance(value.get("files"), list) or not isinstance(value.get("ignore"), list):
        raise GuardError("Manifest files and ignore must be lists")
    if value.get("state_id") != state_id(value["files"]):
        raise GuardError("Manifest state_id does not match its file inventory")
    return value


def compare(
    baseline: dict[str, Any],
    current: dict[str, Any],
    allowed_paths: list[str],
    allowed_new_paths: list[str],
) -> dict[str, Any]:
    before = {item["path"]: item for item in baseline["files"]}
    after = {item["path"]: item for item in current["files"]}
    added = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    violations = [
        {"path": path, "change": "ADDED"}
        for path in added
        if not any(matches(path, pattern) for pattern in allowed_new_paths)
    ]
    violations.extend(
        {"path": path, "change": "DELETED"}
        for path in deleted
        if not any(matches(path, pattern) for pattern in allowed_paths)
    )
    violations.extend(
        {"path": path, "change": "MODIFIED"}
        for path in modified
        if not any(matches(path, pattern) for pattern in allowed_paths)
    )
    return {
        "valid": not violations,
        "baseline_state_id": baseline["state_id"],
        "current_state_id": current["state_id"],
        "changes": {"added": added, "deleted": deleted, "modified": modified},
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            ignores = [] if args.no_default_ignores else list(DEFAULT_IGNORES)
            ignores.extend(args.ignore)
            if any(not valid_pattern(item, allow_control=True) for item in ignores):
                raise GuardError("Invalid ignore matcher")
            root = Path(args.root).expanduser().resolve()
            manifest = create_manifest(root, ignores)
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                with output.open("x", encoding="utf-8") as handle:
                    json.dump(manifest, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
            except FileExistsError as exc:
                raise GuardError(f"Manifest already exists: {output}") from exc
            report: dict[str, Any] = {
                "status": "SNAPSHOT_CREATED",
                "manifest": str(output),
                "workspace_root": manifest["workspace_root"],
                "workspace_id": manifest["workspace_id"],
                "state_id": manifest["state_id"],
                "files": len(manifest["files"]),
            }
            exit_code = 0
        elif args.command == "verify":
            baseline = load_manifest(Path(args.manifest).expanduser().resolve())
            root = Path(args.root or baseline["workspace_root"]).expanduser().resolve()
            for pattern in [*args.allowed_path, *args.allowed_new_path]:
                if not valid_pattern(pattern):
                    raise GuardError(f"Invalid allowed path matcher: {pattern}")
            current = create_manifest(root, list(baseline["ignore"]))
            comparison = compare(
                baseline,
                current,
                list(args.allowed_path),
                list(args.allowed_new_path),
            )
            report = {
                "status": "WORKSPACE_VALID" if comparison["valid"] else "WORKSPACE_VIOLATION",
                "workspace_root": str(root),
                **comparison,
            }
            exit_code = 0 if comparison["valid"] else 1
        elif args.command == "prepare-copy":
            source_root = Path(args.source_root).expanduser().resolve()
            workspace_root = Path(args.workspace_root).expanduser().absolute()
            baseline_path = Path(args.baseline_manifest).expanduser().resolve()
            manifest = prepare_copy(source_root, workspace_root, baseline_path)
            report = {
                "status": "WORKSPACE_PREPARED",
                "source_root": str(source_root),
                "workspace_root": str(workspace_root),
                "workspace_id": manifest["workspace_id"],
                "baseline_manifest": str(baseline_path),
                "state_id": manifest["state_id"],
                "files": len(manifest["files"]),
            }
            exit_code = 0
        elif args.command == "integrate":
            source_root = Path(args.source_root).expanduser().resolve()
            workspace_root = Path(args.workspace_root).expanduser().resolve()
            for pattern in [*args.allowed_path, *args.allowed_new_path]:
                if not valid_pattern(pattern):
                    raise GuardError(f"Invalid allowed path matcher: {pattern}")
            source_baseline = load_manifest(Path(args.source_baseline).expanduser().resolve())
            workspace_baseline = load_manifest(Path(args.workspace_baseline).expanduser().resolve())
            integrated, comparison = integrate_workspace(
                source_root=source_root,
                workspace_root=workspace_root,
                source_baseline=source_baseline,
                workspace_baseline=workspace_baseline,
                allowed_paths=list(args.allowed_path),
                allowed_new_paths=list(args.allowed_new_path),
                output_manifest=Path(args.output_manifest).expanduser().resolve(),
                rollback_dir=Path(args.rollback_dir).expanduser().resolve(),
                plan_file=Path(args.plan_file).expanduser().resolve(),
                plan_id=args.plan_id,
                phase_id=args.phase_id,
                expected_plan_sha256=args.expected_plan_sha256,
                expected_document_version=args.expected_document_version,
            )
            report = {
                "status": "WORKSPACE_INTEGRATED",
                "source_root": str(source_root),
                "workspace_root": str(workspace_root),
                "output_manifest": str(Path(args.output_manifest).expanduser().resolve()),
                "state_id": integrated["state_id"],
                "changes": comparison["changes"],
                "rollback_journal": str(
                    Path(args.rollback_dir).expanduser().resolve() / "journal.json"
                ),
            }
            exit_code = 0
        else:
            report = rollback_integration(Path(args.journal).expanduser().resolve())
            exit_code = 0
    except (OSError, ValueError, json.JSONDecodeError, GuardError) as exc:
        print(f"WORKSPACE_GUARD_ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        for key in (
            "manifest",
            "source_root",
            "workspace_root",
            "workspace_id",
            "baseline_manifest",
            "output_manifest",
            "rollback_journal",
            "journal",
            "state_id",
            "files",
        ):
            if key in report:
                print(f"{key}: {report[key]}")
        for violation in report.get("violations", []):
            print(f"- {violation['change']}: {violation['path']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
