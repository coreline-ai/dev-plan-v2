#!/usr/bin/env python3
"""Core parser, serializer, validator, generator, and state events for v2 plans."""

from __future__ import annotations

import copy
import contextlib
import dataclasses
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

import yaml
from markdown_it import MarkdownIt
from yaml.events import AliasEvent

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised by runtime preflight on non-POSIX hosts
    fcntl = None  # type: ignore[assignment]

try:
    from .workspace_guard import (
        DEFAULT_IGNORES as WORKSPACE_DEFAULT_IGNORES,
        GuardError as WorkspaceGuardError,
        IntegrationLock,
        collect as collect_workspace,
        rollback_integration,
        state_id as workspace_state_id,
        update_json_atomic,
        write_manifest_exclusive,
    )
except ImportError:
    from workspace_guard import (  # type: ignore
        DEFAULT_IGNORES as WORKSPACE_DEFAULT_IGNORES,
        GuardError as WorkspaceGuardError,
        IntegrationLock,
        collect as collect_workspace,
        rollback_integration,
        state_id as workspace_state_id,
        update_json_atomic,
        write_manifest_exclusive,
    )


SCHEMA = "codex-dev-plan/v2"
MAX_FILE_BYTES = 1_048_576
MAX_SCALAR_BYTES = 65_536
MAX_ENTITIES = 1_000

PLAN_STATUSES = {"DRAFT", "READY", "IN_PROGRESS", "QA", "BLOCKED", "COMPLETED"}
PHASE_STATUSES = {"PENDING", "IN_PROGRESS", "QA", "REWORK_PENDING", "BLOCKED", "DONE"}
TASK_STATUSES = {
    "PENDING",
    "ASSIGNED",
    "IN_PROGRESS",
    "WORKER_DONE",
    "REWORK",
    "BLOCKED",
    "DONE",
}
TEST_STATUSES = {"PENDING", "RUNNING", "PASS", "FAIL", "BLOCKED"}
QA_STATUSES = {"PENDING", "RUNNING", "FINISHED"}
QA_VERDICTS = {"PENDING", "PASS", "FAIL", "BLOCKED"}
VALIDITIES = {"VALID", "INVALID", "STALE"}
WORKER_TIERS = {"UNASSIGNED", "TERRA", "LUNA"}
COMPLEXITIES = {"ROUTINE", "COMPLEX"}

TOP_H2_ORDER = [
    "개발 목적",
    "개발 범위",
    "제외 범위",
    "참조 문서",
    "공통 진행 규칙",
    "Phase 상태 요약",
    "QA 관점",
]
FINAL_H2_ORDER = ["최종 통합 QA", "최종 승인"]

PLAN_ID_RE = re.compile(r"^PLAN-(\d{8})-(\d{6})$")
FILENAME_RE = re.compile(r"^implement_(\d{8})_(\d{6})\.md$")
PHASE_HEADING_RE = re.compile(r"^Phase ([1-9][0-9]*)\. (.+)$")
DEV_HEADING_RE = re.compile(r"^(DEV-[0-9]{3,}) (.+)$")
TEST_HEADING_RE = re.compile(r"^(TEST-[0-9]{3,}) (.+)$")
QA_HEADING_RE = re.compile(r"^(QA-[0-9]{3,}|QA-FINAL) (.+)$")
RESTRICTED_PATH_RE = re.compile(r"^(?:[^/*?{}\[\]\\\x00]+/)*(?:[^/*?{}\[\]\\\x00]+|[^/*?{}\[\]\\\x00]+/\*\*)$")

PLACEHOLDER_RE = re.compile(
    r"(?:\bTODO\b|\[TODO\]|\bUNSET\b|목표를 적는다|테스트를 실행한다|"
    r"세부 구현 작업을 추가한다|이번 개발의 목적을 명확하게 적는다)",
    re.IGNORECASE,
)


class PlanError(Exception):
    """Base error with a stable error code."""

    def __init__(self, code: str, message: str, *, entity: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.entity = entity

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.entity:
            value["entity"] = self.entity
        return value


class StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects aliases, merges, and duplicate keys."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            event = self.peek_event()
            raise PlanError("YAML_ALIAS_FORBIDDEN", f"YAML alias is forbidden at {event.start_mark}")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            if getattr(key_node, "value", None) == "<<":
                raise PlanError("YAML_MERGE_FORBIDDEN", "YAML merge keys are forbidden")
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise PlanError("YAML_DUPLICATE_KEY", f"Duplicate YAML key: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


# Keep timestamps as strings for deterministic cross-runtime behavior.
StrictSafeLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for first_char, resolvers in list(StrictSafeLoader.yaml_implicit_resolvers.items()):
    StrictSafeLoader.yaml_implicit_resolvers[first_char] = [
        item for item in resolvers if item[0] != "tag:yaml.org,2002:timestamp"
    ]


class StableDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def load_yaml(text: str, *, source: str = "YAML") -> dict[str, Any]:
    try:
        value = yaml.load(text, Loader=StrictSafeLoader)
    except PlanError:
        raise
    except yaml.YAMLError as exc:
        raise PlanError("YAML_INVALID", f"{source}: {exc}") from exc
    if not isinstance(value, dict):
        raise PlanError("YAML_NOT_MAPPING", f"{source} must be a YAML mapping")
    _validate_yaml_limits(value)
    return value


def dump_yaml(value: dict[str, Any]) -> str:
    return yaml.dump(
        value,
        Dumper=StableDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    ).rstrip()


def _validate_yaml_limits(value: Any, *, depth: int = 0, count: list[int] | None = None) -> None:
    if count is None:
        count = [0]
    if depth > 20:
        raise PlanError("YAML_TOO_DEEP", "YAML nesting depth exceeds 20")
    count[0] += 1
    if count[0] > 10_000:
        raise PlanError("YAML_TOO_LARGE", "YAML collection item limit exceeds 10000")
    if isinstance(value, str) and len(value.encode("utf-8")) > MAX_SCALAR_BYTES:
        raise PlanError("YAML_SCALAR_TOO_LARGE", "YAML scalar exceeds 64 KiB")
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_yaml_limits(key, depth=depth + 1, count=count)
            _validate_yaml_limits(item, depth=depth + 1, count=count)
    elif isinstance(value, list):
        for item in value:
            _validate_yaml_limits(item, depth=depth + 1, count=count)
    elif value is not None and not isinstance(value, (str, int, bool, float)):
        raise PlanError("YAML_TYPE_FORBIDDEN", f"Unsupported YAML type: {type(value).__name__}")


@dataclasses.dataclass
class Heading:
    level: int
    title: str
    line: int


@dataclasses.dataclass
class EntityBlock:
    kind: str
    entity_id: str
    title: str
    heading_line: int
    yaml_start: int
    yaml_end: int
    data: dict[str, Any]
    checkbox_line: int | None = None
    phase_id: str | None = None


@dataclasses.dataclass
class PlanDocument:
    path: Path
    text: str
    lines: list[str]
    metadata: dict[str, Any]
    metadata_start: int
    metadata_end: int
    h1: str
    headings: list[Heading]
    blocks: list[EntityBlock]

    def blocks_of(self, kind: str) -> list[EntityBlock]:
        return [block for block in self.blocks if block.kind == kind]

    def entity(self, entity_id: str) -> EntityBlock:
        matches = [block for block in self.blocks if block.entity_id == entity_id]
        if len(matches) != 1:
            raise PlanError("ENTITY_NOT_FOUND", f"Expected one entity {entity_id}, found {len(matches)}")
        return matches[0]

    def clone(self) -> "PlanDocument":
        return copy.deepcopy(self)

    def render(self) -> str:
        replacements: list[tuple[int, int, list[str]]] = []
        replacements.append(
            (self.metadata_start, self.metadata_end, dump_yaml(self.metadata).splitlines())
        )
        for block in self.blocks:
            replacements.append((block.yaml_start, block.yaml_end, dump_yaml(block.data).splitlines()))

        checkbox_values: dict[int, bool] = {}
        for block in self.blocks:
            if block.checkbox_line is None:
                continue
            if block.kind == "task":
                checkbox_values[block.checkbox_line] = block.data.get("status") == "DONE"
            elif block.kind == "test":
                checkbox_values[block.checkbox_line] = block.data.get("status") == "PASS"
            elif block.kind == "qa":
                checkbox_values[block.checkbox_line] = (
                    block.data.get("status") == "FINISHED"
                    and block.data.get("verdict") == "PASS"
                )

        phase_done = {
            block.entity_id: block.data.get("status") == "DONE"
            for block in self.blocks_of("phase")
        }
        for index, line in enumerate(self.lines):
            if index in checkbox_values:
                mark = "x" if checkbox_values[index] else " "
                replacements.append((index, index + 1, [re.sub(r"- \[[ xX]\]", f"- [{mark}]", line, count=1)]))
                continue
            summary = re.match(r"^-\s+\[[ xX]\]\s+(P[0-9]+)\s+.+완료\s*$", line)
            if summary and summary.group(1) in phase_done:
                mark = "x" if phase_done[summary.group(1)] else " "
                replacements.append((index, index + 1, [re.sub(r"- \[[ xX]\]", f"- [{mark}]", line, count=1)]))

        # Phase completion checkboxes are all derived from Phase DONE.
        phase_ranges = _phase_line_ranges(self)
        for phase_id, (start, end) in phase_ranges.items():
            mark = "x" if phase_done.get(phase_id, False) else " "
            completion_line = _find_heading_line(self.headings, "완료 조건", 3, start, end)
            if completion_line is not None:
                for index in range(completion_line + 1, end):
                    if re.match(r"^-\s+\[[ xX]\]", self.lines[index]):
                        replacements.append(
                            (index, index + 1, [re.sub(r"- \[[ xX]\]", f"- [{mark}]", self.lines[index], count=1)])
                        )

        final_start = _find_heading_line(self.headings, "최종 승인", 2, 0, len(self.lines))
        if final_start is not None:
            final_qa = next((b for b in self.blocks_of("qa") if b.entity_id == "QA-FINAL"), None)
            final_values = [
                all(phase_done.values()) if phase_done else False,
                bool(final_qa and final_qa.data.get("status") == "FINISHED" and final_qa.data.get("verdict") == "PASS"),
                self.metadata.get("final_approval") == "APPROVED",
                self.metadata.get("final_approval") == "APPROVED",
            ]
            cursor = 0
            for index in range(final_start + 1, len(self.lines)):
                if re.match(r"^-\s+\[[ xX]\]", self.lines[index]) and cursor < len(final_values):
                    mark = "x" if final_values[cursor] else " "
                    replacements.append(
                        (index, index + 1, [re.sub(r"- \[[ xX]\]", f"- [{mark}]", self.lines[index], count=1)])
                    )
                    cursor += 1

        result = list(self.lines)
        # Later duplicate replacements for the same line are equivalent; last one wins.
        normalized: dict[tuple[int, int], list[str]] = {}
        for start, end, value in replacements:
            normalized[(start, end)] = value
        for (start, end), value in sorted(normalized.items(), key=lambda item: item[0][0], reverse=True):
            result[start:end] = value
        return "\n".join(result).rstrip() + "\n"


def parse_plan(path: str | Path, *, text: str | None = None) -> PlanDocument:
    plan_path = Path(path).expanduser().resolve()
    if text is None:
        raw = plan_path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise PlanError("PLAN_TOO_LARGE", "Plan file exceeds 1 MiB")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlanError("PLAN_ENCODING", "Plan file must be UTF-8") from exc
    if "\r" in text:
        raise PlanError("PLAN_LINE_ENDING", "Plan file must use LF line endings")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0] != "---":
        raise PlanError("FRONTMATTER_MISSING", "Plan must start with YAML frontmatter")
    try:
        frontmatter_end = lines.index("---", 1)
    except ValueError as exc:
        raise PlanError("FRONTMATTER_UNCLOSED", "YAML frontmatter is not closed") from exc
    metadata = load_yaml("\n".join(lines[1:frontmatter_end]), source="frontmatter")

    tokens = MarkdownIt("commonmark").parse(text)
    headings: list[Heading] = []
    fences: list[Any] = []
    h1 = ""
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.map:
            level = int(token.tag[1:])
            title = tokens[index + 1].content.strip() if index + 1 < len(tokens) else ""
            heading = Heading(level=level, title=title, line=token.map[0])
            headings.append(heading)
            if level == 1 and not h1:
                h1 = title
        elif token.type == "fence" and token.map and token.info.strip() == "yaml":
            fences.append(token)

    if not h1:
        raise PlanError("H1_MISSING", "Plan must have an H1 filename heading")

    entity_headings: list[tuple[str, str, str, Heading, str | None]] = []
    phase_context: str | None = None
    for heading in headings:
        phase_match = PHASE_HEADING_RE.match(heading.title) if heading.level == 2 else None
        if phase_match:
            phase_context = f"P{phase_match.group(1)}"
            entity_headings.append(("phase", phase_context, phase_match.group(2), heading, phase_context))
            continue
        if heading.level == 2 and heading.title == "최종 통합 QA":
            phase_context = None
            continue
        if heading.level != 4:
            continue
        for kind, pattern in (
            ("task", DEV_HEADING_RE),
            ("test", TEST_HEADING_RE),
            ("qa", QA_HEADING_RE),
        ):
            match = pattern.match(heading.title)
            if match:
                entity_id = match.group(1)
                entity_headings.append((kind, entity_id, match.group(2), heading, phase_context))
                break

    if len(entity_headings) > MAX_ENTITIES:
        raise PlanError("ENTITY_LIMIT", "Plan contains more than 1000 entities")

    blocks: list[EntityBlock] = []
    heading_lines = sorted(heading.line for heading in headings)
    for kind, entity_id, title, heading, phase_id in entity_headings:
        next_heading_line = min(
            (line for line in heading_lines if line > heading.line),
            default=len(lines),
        )
        candidates = [
            fence
            for fence in fences
            if fence.map[0] > heading.line and fence.map[0] < next_heading_line
        ]
        if len(candidates) != 1:
            raise PlanError(
                "ENTITY_YAML_COUNT",
                f"{entity_id} must contain exactly one YAML state block; found {len(candidates)}",
                entity=entity_id,
            )
        fence = candidates[0]
        data = load_yaml(fence.content, source=entity_id)
        checkbox_line: int | None = None
        if kind != "phase":
            for line_index in range(fence.map[1], next_heading_line):
                stripped = lines[line_index].strip()
                if not stripped:
                    continue
                if re.match(r"^-\s+\[[ xX]\]\s+완료\s*$", stripped):
                    checkbox_line = line_index
                break
            if checkbox_line is None:
                raise PlanError("ENTITY_CHECKBOX_MISSING", f"{entity_id} completion checkbox is missing", entity=entity_id)
        blocks.append(
            EntityBlock(
                kind=kind,
                entity_id=entity_id,
                title=title,
                heading_line=heading.line,
                yaml_start=fence.map[0] + 1,
                yaml_end=fence.map[1] - 1,
                data=data,
                checkbox_line=checkbox_line,
                phase_id=phase_id,
            )
        )

    return PlanDocument(
        path=plan_path,
        text=text,
        lines=lines,
        metadata=metadata,
        metadata_start=1,
        metadata_end=frontmatter_end,
        h1=h1,
        headings=headings,
        blocks=blocks,
    )


def _find_heading_line(
    headings: list[Heading],
    title: str,
    level: int,
    start: int,
    end: int,
) -> int | None:
    for heading in headings:
        if heading.level == level and heading.title == title and start <= heading.line < end:
            return heading.line
    return None


def _phase_line_ranges(doc: PlanDocument) -> dict[str, tuple[int, int]]:
    phase_blocks = sorted(doc.blocks_of("phase"), key=lambda block: block.heading_line)
    result: dict[str, tuple[int, int]] = {}
    for index, block in enumerate(phase_blocks):
        end = phase_blocks[index + 1].heading_line if index + 1 < len(phase_blocks) else len(doc.lines)
        final_line = _find_heading_line(doc.headings, "최종 통합 QA", 2, block.heading_line, end)
        if final_line is not None:
            end = final_line
        result[block.entity_id] = (block.heading_line, end)
    return result


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def workspace_id_for_root(root: Path) -> str:
    canonical = str(root.expanduser().resolve())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def validate_workspace_identity(
    workspace_root: Any,
    workspace_id: Any,
    *,
    project_root: Path,
    require_disposable: bool,
) -> list[PlanError]:
    if not _is_nonempty_string(workspace_root) or not _is_nonempty_string(workspace_id):
        return [PlanError("WORKSPACE_IDENTITY_INVALID", "Workspace root and ID are required")]
    try:
        declared = str(workspace_root)
        canonical_root = Path(declared).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        return [PlanError("WORKSPACE_IDENTITY_INVALID", str(exc))]
    if not Path(declared).is_absolute() or declared != str(canonical_root):
        return [
            PlanError(
                "WORKSPACE_IDENTITY_INVALID",
                "workspace_root must be a canonical absolute path",
            )
        ]
    expected_id = workspace_id_for_root(canonical_root)
    if workspace_id != expected_id:
        return [
            PlanError(
                "WORKSPACE_IDENTITY_INVALID",
                "workspace_id does not match the canonical workspace_root",
            )
        ]
    if require_disposable and canonical_root.is_relative_to(project_root.expanduser().resolve()):
        return [
            PlanError(
                "WORKSPACE_NOT_DISPOSABLE",
                "MANIFEST_GUARDED workspace_root must be outside the source project root",
            )
        ]
    return []


def project_root_for(plan_path: Path) -> Path:
    return plan_path.parent.parent if plan_path.parent.name == "dev-plan" else plan_path.parent


def evidence_ref(
    path: str,
    *,
    project_root: Path,
) -> dict[str, Any]:
    target = (project_root / path).resolve()
    root = project_root.resolve()
    if not target.is_relative_to(root):
        raise PlanError("EVIDENCE_PATH_ESCAPE", f"Evidence path escapes project root: {path}")
    if not target.is_file():
        raise PlanError("EVIDENCE_MISSING", f"Evidence file does not exist: {path}")
    return {"path": path, "sha256": file_sha256(target), "bytes": target.stat().st_size}


def validate_evidence_shape(ref: Any, *, required: bool = True) -> list[PlanError]:
    if ref in (None, "NONE", "UNSET"):
        return [PlanError("EVIDENCE_MISSING", "Evidence reference is missing")] if required else []
    if not isinstance(ref, dict):
        return [PlanError("EVIDENCE_INVALID", "Evidence reference must be a mapping")]
    errors: list[PlanError] = []
    for key in ("path", "sha256", "bytes"):
        if key not in ref:
            errors.append(PlanError("EVIDENCE_FIELD_MISSING", f"Evidence reference is missing {key}"))
    if errors:
        return errors
    if not isinstance(ref["path"], str) or not ref["path"].strip():
        errors.append(PlanError("EVIDENCE_INVALID", "Evidence path must be a non-empty string"))
    if not isinstance(ref["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]):
        errors.append(PlanError("EVIDENCE_INVALID", "Evidence sha256 must be 64 lowercase hex characters"))
    if not isinstance(ref["bytes"], int) or isinstance(ref["bytes"], bool) or ref["bytes"] < 0:
        errors.append(PlanError("EVIDENCE_INVALID", "Evidence bytes must be a non-negative integer"))
    return errors


def validate_evidence_reference(
    ref: Any,
    *,
    project_root: Path,
    required: bool = True,
) -> list[PlanError]:
    errors = validate_evidence_shape(ref, required=required)
    if errors:
        return errors
    try:
        path = (project_root / str(ref["path"])).resolve()
        if not path.is_relative_to(project_root.resolve()):
            raise PlanError("EVIDENCE_PATH_ESCAPE", f"Evidence path escapes project root: {ref['path']}")
        if not path.is_file():
            raise PlanError("EVIDENCE_MISSING", f"Evidence file does not exist: {ref['path']}")
        if path.stat().st_size != int(ref["bytes"]):
            raise PlanError("EVIDENCE_SIZE_MISMATCH", f"Evidence size mismatch: {ref['path']}")
        if file_sha256(path) != str(ref["sha256"]):
            raise PlanError("EVIDENCE_HASH_MISMATCH", f"Evidence SHA-256 mismatch: {ref['path']}")
    except PlanError as exc:
        errors.append(exc)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(PlanError("EVIDENCE_INVALID", str(exc)))
    return errors


def validate_evidence_manifest_reference(
    ref: Any,
    *,
    project_root: Path,
    expected_plan_id: str,
    expected_entity_id: str,
    expected_stage: str,
    expected_attempt: int | None = None,
    check_current_state: bool = False,
    expected_workspace_root: str | None = None,
    expected_workspace_id: str | None = None,
    require_disposable_workspace: bool = False,
) -> list[PlanError]:
    errors = validate_evidence_reference(ref, project_root=project_root)
    if errors:
        return errors
    path = (project_root / str(ref["path"])).resolve()
    evidence_root = (project_root / "dev-plan" / "evidence" / expected_plan_id).resolve()
    if not path.is_relative_to(evidence_root):
        return [
            PlanError(
                "EVIDENCE_PATH_INVALID",
                f"Evidence manifest must be under dev-plan/evidence/{expected_plan_id}/",
            )
        ]
    if expected_stage == "BASELINE" and not path.is_relative_to(evidence_root / "baseline"):
        return [PlanError("EVIDENCE_PATH_INVALID", "BASELINE manifest must be under the baseline directory")]
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise PlanError("EVIDENCE_MANIFEST_TOO_LARGE", "Evidence manifest exceeds 1 MiB")
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if path.suffix.lower() == ".json" else load_yaml(text, source=str(path))
    except (OSError, UnicodeError, json.JSONDecodeError, PlanError) as exc:
        return [exc] if isinstance(exc, PlanError) else [PlanError("EVIDENCE_MANIFEST_INVALID", str(exc))]
    required = {
        "manifest_version": "codex-evidence-manifest/v1",
        "plan_id": expected_plan_id,
        "entity_id": expected_entity_id,
        "stage": expected_stage,
    }
    for field, expected in required.items():
        if value.get(field) != expected:
            errors.append(
                PlanError(
                    "EVIDENCE_MANIFEST_INVALID",
                    f"Evidence manifest {field} must be {expected}, got {value.get(field)}",
                )
            )
    attempt = value.get("attempt")
    if not _is_nonnegative_int(attempt):
        errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence manifest attempt must be non-negative"))
    elif expected_attempt is not None and attempt != expected_attempt:
        errors.append(
            PlanError(
                "EVIDENCE_MANIFEST_INVALID",
                f"Evidence manifest attempt must be {expected_attempt}, got {attempt}",
            )
        )
    if value.get("validity") not in {"VALID", "INVALID", "STALE"}:
        errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence manifest validity is invalid"))
    elif value.get("validity") != "VALID":
        errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "State-gating evidence manifest must be VALID"))
    if not _valid_iso_datetime(value.get("created_at")):
        errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence manifest created_at is invalid"))
    files = value.get("files")
    workspace_entries: list[dict[str, Any]] = []
    role_entries: dict[str, dict[str, Any]] = {}
    if not isinstance(files, list) or not files:
        errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence manifest files must be a non-empty list"))
    else:
        paths: list[str] = []
        roles: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict):
                errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence files entries must be mappings"))
                continue
            role = entry.get("role")
            if not _is_nonempty_string(role) or role in roles:
                errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence file role must be unique and non-empty"))
            else:
                roles.add(role)
                role_entries[str(role)] = entry
                if role == "workspace_manifest":
                    workspace_entries.append(entry)
            paths.append(str(entry.get("path", "")))
            entry_errors = validate_evidence_reference(entry, project_root=project_root)
            errors.extend(entry_errors)
            if isinstance(entry.get("path"), str):
                entry_path = (project_root / entry["path"]).resolve()
                if not entry_path.is_relative_to(evidence_root):
                    errors.append(PlanError("EVIDENCE_PATH_INVALID", "Evidence file escapes the Plan evidence root"))
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence files must be path-sorted and unique"))
        required_roles: set[str] = set()
        if expected_stage == "INPUT":
            if expected_entity_id.startswith("DEV-"):
                required_roles = {"worker_contract", "workspace_manifest"}
            elif expected_entity_id.startswith("TEST-"):
                required_roles = {"workspace_manifest"}
            elif expected_entity_id.startswith("QA-"):
                required_roles = {"qa_contract", "workspace_manifest"}
        elif expected_stage == "RESULT":
            if expected_entity_id.startswith("DEV-"):
                required_roles = {"worker_report", "pre_state", "post_state", "diff", "test_log"}
            elif expected_entity_id.startswith("TEST-"):
                required_roles = {"test_log", "post_state"}
            elif expected_entity_id.startswith("QA-"):
                required_roles = {"qa_response", "qa_report", "pre_state", "post_state"}
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            errors.append(
                PlanError(
                    "EVIDENCE_MANIFEST_INVALID",
                    f"Evidence manifest is missing required roles: {missing_roles}",
                )
            )
    if expected_stage == "BASELINE":
        if not _is_nonempty_string(value.get("output_state_id")):
            errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "BASELINE requires output_state_id"))
        if len(workspace_entries) != 1:
            errors.append(
                PlanError(
                    "EVIDENCE_MANIFEST_INVALID",
                    "BASELINE requires exactly one workspace_manifest file",
                )
            )
        else:
            workspace_path = (project_root / str(workspace_entries[0].get("path"))).resolve()
            try:
                workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
                if workspace.get("schema") != "codex-workspace-manifest/v1":
                    raise PlanError("EVIDENCE_MANIFEST_INVALID", "workspace_manifest schema is invalid")
                if Path(str(workspace.get("workspace_root"))).resolve() != project_root.resolve():
                    raise PlanError("EVIDENCE_MANIFEST_INVALID", "BASELINE workspace_root must equal project root")
                if workspace.get("ignore") != WORKSPACE_DEFAULT_IGNORES:
                    raise PlanError("EVIDENCE_MANIFEST_INVALID", "workspace_manifest ignore policy is not canonical")
                inventory = workspace.get("files")
                if not isinstance(inventory, list) or workspace.get("state_id") != workspace_state_id(inventory):
                    raise PlanError("EVIDENCE_MANIFEST_INVALID", "workspace_manifest state_id is invalid")
                if value.get("output_state_id") != workspace.get("state_id"):
                    raise PlanError("EVIDENCE_MANIFEST_INVALID", "BASELINE output_state_id differs from workspace state")
                if check_current_state:
                    current_state = workspace_state_id(
                        collect_workspace(project_root.resolve(), list(WORKSPACE_DEFAULT_IGNORES))
                    )
                    if current_state != workspace.get("state_id"):
                        raise PlanError("EVIDENCE_STATE_MISMATCH", "Current protected tree differs from BASELINE")
            except (OSError, ValueError, json.JSONDecodeError, PlanError, WorkspaceGuardError) as exc:
                errors.append(
                    exc
                    if isinstance(exc, PlanError)
                    else PlanError("EVIDENCE_MANIFEST_INVALID", str(exc))
                )
    elif expected_stage == "INPUT":
        if not _is_nonempty_string(value.get("input_state_id")):
            errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", "INPUT requires input_state_id"))
    elif expected_stage == "RESULT":
        for field in ("input_state_id", "output_state_id"):
            if not _is_nonempty_string(value.get(field)):
                errors.append(PlanError("EVIDENCE_MANIFEST_INVALID", f"RESULT requires {field}"))
        input_manifest = value.get("input_manifest")
        errors.extend(validate_evidence_reference(input_manifest, project_root=project_root))
        if isinstance(input_manifest, dict) and isinstance(input_manifest.get("path"), str):
            input_path = (project_root / input_manifest["path"]).resolve()
            if not input_path.is_relative_to(evidence_root):
                errors.append(PlanError("EVIDENCE_PATH_INVALID", "input_manifest escapes the Plan evidence root"))
            else:
                errors.extend(
                    validate_evidence_manifest_reference(
                        input_manifest,
                        project_root=project_root,
                        expected_plan_id=expected_plan_id,
                        expected_entity_id=expected_entity_id,
                        expected_stage="INPUT",
                        expected_attempt=expected_attempt,
                        check_current_state=False,
                    )
                )

    workspace_role_states: dict[str, Any] = {}
    if expected_stage in {"BASELINE", "INPUT"}:
        workspace_role_states["workspace_manifest"] = value.get(
            "output_state_id" if expected_stage == "BASELINE" else "input_state_id"
        )
    if expected_stage == "RESULT":
        workspace_role_states["pre_state"] = value.get("input_state_id")
        workspace_role_states["post_state"] = value.get("output_state_id")
    for role, expected_state in workspace_role_states.items():
        entry = role_entries.get(role)
        if entry is None:
            continue
        artifact_path = (project_root / str(entry.get("path", ""))).resolve()
        try:
            workspace_value = json.loads(artifact_path.read_text(encoding="utf-8"))
            inventory = workspace_value.get("files")
            identity_errors = validate_workspace_identity(
                workspace_value.get("workspace_root"),
                workspace_value.get("workspace_id"),
                project_root=project_root,
                require_disposable=require_disposable_workspace,
            )
            if identity_errors:
                raise identity_errors[0]
            if (
                workspace_value.get("schema") != "codex-workspace-manifest/v1"
                or workspace_value.get("ignore") != WORKSPACE_DEFAULT_IGNORES
                or not isinstance(inventory, list)
                or workspace_value.get("state_id") != workspace_state_id(inventory)
                or workspace_value.get("state_id") != expected_state
                or (
                    expected_workspace_root is not None
                    and Path(str(workspace_value.get("workspace_root"))).resolve()
                    != Path(expected_workspace_root).resolve()
                )
                or (
                    expected_workspace_id is not None
                    and workspace_value.get("workspace_id") != expected_workspace_id
                )
            ):
                raise PlanError(
                    "EVIDENCE_MANIFEST_INVALID",
                    f"{role} is not a canonical workspace manifest for the declared state",
                )
        except (OSError, ValueError, json.JSONDecodeError, PlanError) as exc:
            errors.append(
                exc
                if isinstance(exc, PlanError)
                else PlanError("EVIDENCE_MANIFEST_INVALID", str(exc))
            )
    return errors


def validate_runtime_attestation_reference(
    ref: Any,
    *,
    project_root: Path,
    expected_agent_id: str,
    expected_role: str,
    expected_model: str,
    expected_tier: str | None = None,
) -> tuple[dict[str, Any] | None, list[PlanError]]:
    errors = validate_evidence_reference(ref, project_root=project_root)
    if errors:
        return None, errors
    path = (project_root / str(ref["path"])).resolve()
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise PlanError("RUNTIME_ATTESTATION_INVALID", "Runtime attestation exceeds 1 MiB")
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if path.suffix.lower() == ".json" else load_yaml(text, source=str(path))
    except (OSError, UnicodeError, json.JSONDecodeError, PlanError) as exc:
        error = exc if isinstance(exc, PlanError) else PlanError("RUNTIME_ATTESTATION_INVALID", str(exc))
        return None, [error]
    checks = {
        "schema": "codex-runtime-attestation/v1",
        "agent_id": expected_agent_id,
        "role": expected_role,
        "requested_model": expected_model,
        "context_mode": "NONE",
    }
    if expected_tier is not None:
        checks["worker_tier"] = expected_tier
    for field, expected in checks.items():
        if value.get(field) != expected:
            errors.append(
                PlanError(
                    "RUNTIME_ATTESTATION_INVALID",
                    f"Runtime attestation {field} must be {expected}, got {value.get(field)}",
                )
            )
    supported = value.get("supported_models")
    if not isinstance(supported, list) or expected_model not in supported:
        errors.append(PlanError("RUNTIME_ATTESTATION_INVALID", "requested_model is absent from supported_models"))
    if value.get("actual_model") not in {expected_model, "NOT_REPORTED"}:
        errors.append(PlanError("RUNTIME_ATTESTATION_INVALID", "actual_model conflicts with requested_model"))
    for field in ("workspace_root", "workspace_id", "spawn_receipt_sha256"):
        if not _is_nonempty_string(value.get(field)):
            errors.append(PlanError("RUNTIME_ATTESTATION_INVALID", f"{field} is required"))
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("spawn_receipt_sha256", ""))):
        errors.append(PlanError("RUNTIME_ATTESTATION_INVALID", "spawn_receipt_sha256 must be 64 lowercase hex"))
    if not _valid_iso_datetime(value.get("created_at")):
        errors.append(PlanError("RUNTIME_ATTESTATION_INVALID", "created_at is invalid"))

    nested_values: dict[str, dict[str, Any]] = {}
    evidence_root = (project_root / "dev-plan" / "evidence").resolve()
    for field in ("model_enum_snapshot", "spawn_receipt"):
        nested_ref = value.get(field)
        nested_errors = validate_evidence_reference(nested_ref, project_root=project_root)
        errors.extend(nested_errors)
        if nested_errors or not isinstance(nested_ref, dict):
            continue
        nested_path = (project_root / str(nested_ref["path"])).resolve()
        if not nested_path.is_relative_to(evidence_root):
            errors.append(
                PlanError(
                    "RUNTIME_ATTESTATION_INVALID",
                    f"{field} must be under dev-plan/evidence/",
                )
            )
            continue
        try:
            nested_text = nested_path.read_text(encoding="utf-8")
            nested_value = (
                json.loads(nested_text)
                if nested_path.suffix.lower() == ".json"
                else load_yaml(nested_text, source=str(nested_path))
            )
            if not isinstance(nested_value, dict):
                raise PlanError(
                    "RUNTIME_ATTESTATION_INVALID",
                    f"{field} must contain a mapping",
                )
            nested_values[field] = nested_value
        except (OSError, UnicodeError, json.JSONDecodeError, PlanError) as exc:
            errors.append(
                exc
                if isinstance(exc, PlanError)
                else PlanError("RUNTIME_ATTESTATION_INVALID", str(exc))
            )

    snapshot = nested_values.get("model_enum_snapshot")
    if snapshot is not None:
        snapshot_models = snapshot.get("models")
        if (
            snapshot.get("schema") != "codex-model-enum-snapshot/v1"
            or not _is_nonempty_string(snapshot.get("runtime_source"))
            or not isinstance(snapshot_models, list)
            or any(not _is_nonempty_string(item) for item in snapshot_models)
            or len(snapshot_models) != len(set(snapshot_models))
            or snapshot_models != supported
            or expected_model not in snapshot_models
            or not _valid_iso_datetime(snapshot.get("created_at"))
        ):
            errors.append(
                PlanError(
                    "RUNTIME_ATTESTATION_INVALID",
                    "model_enum_snapshot is invalid or differs from supported_models",
                )
            )

    receipt = nested_values.get("spawn_receipt")
    receipt_ref = value.get("spawn_receipt")
    if receipt is not None:
        receipt_checks = {
            "schema": "codex-spawn-receipt/v1",
            "status": "SPAWNED",
            "agent_id": expected_agent_id,
            "role": expected_role,
            "requested_model": expected_model,
            "context_mode": "NONE",
            "workspace_root": value.get("workspace_root"),
            "workspace_id": value.get("workspace_id"),
        }
        if any(receipt.get(field) != expected for field, expected in receipt_checks.items()):
            errors.append(
                PlanError(
                    "RUNTIME_ATTESTATION_INVALID",
                    "spawn_receipt is not bound to this agent/model/workspace",
                )
            )
        if (
            receipt.get("actual_model") not in {expected_model, "NOT_REPORTED"}
            or not _valid_iso_datetime(receipt.get("created_at"))
        ):
            errors.append(PlanError("RUNTIME_ATTESTATION_INVALID", "spawn_receipt result is invalid"))
        if (
            not isinstance(receipt_ref, dict)
            or receipt_ref.get("sha256") != value.get("spawn_receipt_sha256")
        ):
            errors.append(
                PlanError(
                    "RUNTIME_ATTESTATION_INVALID",
                    "spawn_receipt_sha256 differs from the receipt reference",
                )
            )
    return value, errors


def validate_approval_evidence_reference(
    ref: Any,
    *,
    project_root: Path,
    expected_plan_id: str,
    expected_kind: str,
    expected_entity_id: str,
    expected_approver_role: str,
) -> tuple[dict[str, Any] | None, list[PlanError]]:
    errors = validate_evidence_reference(ref, project_root=project_root)
    if errors:
        return None, errors
    path = (project_root / str(ref["path"])).resolve()
    evidence_root = (project_root / "dev-plan" / "evidence" / expected_plan_id).resolve()
    if not path.is_relative_to(evidence_root):
        return None, [PlanError("EVIDENCE_PATH_INVALID", "Approval evidence escapes the Plan evidence root")]
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise PlanError("APPROVAL_EVIDENCE_INVALID", "Approval evidence exceeds 1 MiB")
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if path.suffix.lower() == ".json" else load_yaml(text, source=str(path))
    except (OSError, UnicodeError, json.JSONDecodeError, PlanError) as exc:
        error = exc if isinstance(exc, PlanError) else PlanError("APPROVAL_EVIDENCE_INVALID", str(exc))
        return None, [error]
    expected = {
        "schema": "codex-approval-evidence/v1",
        "plan_id": expected_plan_id,
        "approval_kind": expected_kind,
        "entity_id": expected_entity_id,
        "approver_role": expected_approver_role,
        "decision": "ACCEPTED" if expected_kind == "RISK" else "APPROVED",
    }
    for field, wanted in expected.items():
        if value.get(field) != wanted:
            errors.append(
                PlanError(
                    "APPROVAL_EVIDENCE_INVALID",
                    f"Approval evidence {field} must be {wanted}, got {value.get(field)}",
                )
            )
    if not _valid_iso_datetime(value.get("created_at")):
        errors.append(PlanError("APPROVAL_EVIDENCE_INVALID", "Approval created_at is invalid"))
    if not _is_nonempty_string(value.get("statement")):
        errors.append(PlanError("APPROVAL_EVIDENCE_INVALID", "Approval statement is required"))
    return value, errors


def validate_revision_binding(
    revision: Any,
    *,
    evidence_manifest_ref: Any,
    project_root: Path,
    check_current_revision: bool = False,
) -> list[PlanError]:
    if not _is_nonempty_string(revision) or not isinstance(evidence_manifest_ref, dict):
        return [PlanError("REVISION_INVALID", "Revision and evidence manifest are required")]
    manifest_path = (project_root / str(evidence_manifest_ref.get("path", ""))).resolve()
    try:
        text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(text) if manifest_path.suffix.lower() == ".json" else load_yaml(text, source=str(manifest_path))
        output_state_id = manifest.get("output_state_id")
    except (OSError, UnicodeError, json.JSONDecodeError, PlanError) as exc:
        return [exc] if isinstance(exc, PlanError) else [PlanError("REVISION_INVALID", str(exc))]
    if revision.startswith("manifest:"):
        if revision.removeprefix("manifest:") != output_state_id:
            return [PlanError("REVISION_INVALID", "Manifest revision does not match BASELINE output_state_id")]
        return []
    if revision.startswith("git:"):
        expected = revision.removeprefix("git:")
        if not re.fullmatch(r"[0-9a-f]{40,64}", expected):
            return [PlanError("REVISION_INVALID", "Git revision must contain the full commit hash")]
        try:
            command = (
                ["git", "-C", str(project_root), "rev-parse", "HEAD"]
                if check_current_revision
                else ["git", "-C", str(project_root), "cat-file", "-e", f"{expected}^{{commit}}"]
            )
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return [PlanError("REVISION_INVALID", str(exc))]
        if completed.returncode != 0:
            return [PlanError("REVISION_INVALID", "Git revision is unavailable")]
        if check_current_revision and completed.stdout.strip() != expected:
            return [PlanError("REVISION_INVALID", "Git revision does not match current HEAD")]
        return []
    return [PlanError("REVISION_INVALID", "Revision must start with git: or manifest:")]


def _require_fields(data: dict[str, Any], fields: Iterable[str], entity: str) -> list[PlanError]:
    return [
        PlanError("FIELD_MISSING", f"Missing required field: {field}", entity=entity)
        for field in fields
        if field not in data
    ]


def _heading_positions(doc: PlanDocument, titles: list[str]) -> list[int]:
    positions: list[int] = []
    for title in titles:
        matches = [heading.line for heading in doc.headings if heading.level == 2 and heading.title == title]
        if len(matches) != 1:
            raise PlanError("SECTION_COUNT", f"Section '{title}' must appear exactly once; found {len(matches)}")
        positions.append(matches[0])
    return positions


def _checkbox_checked(line: str) -> bool:
    return bool(re.match(r"^-\s+\[[xX]\]", line.strip()))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_iso_datetime(value: Any) -> bool:
    if not _is_nonempty_string(value):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _future_iso_datetime(value: Any) -> bool:
    if not _valid_iso_datetime(value):
        return False
    parsed = dt.datetime.fromisoformat(str(value))
    return parsed > dt.datetime.now(dt.timezone.utc)


def validate_structural(doc: PlanDocument) -> list[PlanError]:
    errors: list[PlanError] = []
    metadata = doc.metadata
    required_meta = [
        "schema",
        "plan_id",
        "status",
        "current_phase",
        "document_version",
        "created_at",
        "updated_at",
        "lead_model",
        "worker_routing",
        "isolation_mode",
        "qa_model",
        "max_rework",
        "qa_timeout_seconds",
        "max_log_bytes",
        "manifest_ignore",
        "planning_revision",
        "planning_evidence",
        "execution_baseline",
        "execution_evidence",
        "final_approval",
        "final_approval_evidence",
        "last_resolution_evidence",
        "residual_risks",
        "finding_ledger",
        "blocked_from",
        "blocked_reason",
        "unblock_conditions",
    ]
    errors.extend(_require_fields(metadata, required_meta, "PLAN"))
    if metadata.get("schema") != SCHEMA:
        errors.append(PlanError("SCHEMA_INVALID", f"schema must be {SCHEMA}", entity="PLAN"))
    if metadata.get("status") not in PLAN_STATUSES:
        errors.append(PlanError("PLAN_STATUS_INVALID", f"Invalid plan status: {metadata.get('status')}", entity="PLAN"))
    if not isinstance(metadata.get("document_version"), int) or int(metadata.get("document_version", -1)) < 0:
        errors.append(PlanError("DOCUMENT_VERSION_INVALID", "document_version must be a non-negative integer"))
    if not isinstance(metadata.get("max_rework"), int) or int(metadata.get("max_rework", -1)) < 0:
        errors.append(PlanError("MAX_REWORK_INVALID", "max_rework must be a non-negative integer"))
    if metadata.get("worker_routing") != "automatic":
        errors.append(PlanError("ROUTING_INVALID", "worker_routing must be automatic"))
    if metadata.get("isolation_mode") not in {"CAPABILITY", "MANIFEST_GUARDED"}:
        errors.append(PlanError("ISOLATION_MODE_INVALID", "isolation_mode is invalid"))
    if metadata.get("manifest_ignore") != WORKSPACE_DEFAULT_IGNORES:
        errors.append(
            PlanError(
                "MANIFEST_IGNORE_INVALID",
                f"manifest_ignore must equal the canonical policy: {WORKSPACE_DEFAULT_IGNORES}",
            )
        )
    for field in ("created_at", "updated_at"):
        if not _valid_iso_datetime(metadata.get(field)):
            errors.append(PlanError("TIMESTAMP_INVALID", f"{field} must be an ISO-8601 timestamp with timezone"))
    for field in ("lead_model", "qa_model"):
        if not _is_nonempty_string(metadata.get(field)) or metadata.get(field) in {"UNSET", "NONE", "UNASSIGNED"}:
            errors.append(PlanError("MODEL_INVALID", f"{field} must be an exact runtime model ID"))
    if not isinstance(metadata.get("qa_timeout_seconds"), int) or int(metadata.get("qa_timeout_seconds", 0)) <= 0:
        errors.append(PlanError("QA_TIMEOUT_INVALID", "qa_timeout_seconds must be positive"))
    if not isinstance(metadata.get("max_log_bytes"), int) or int(metadata.get("max_log_bytes", 0)) <= 0:
        errors.append(PlanError("MAX_LOG_BYTES_INVALID", "max_log_bytes must be positive"))
    if metadata.get("final_approval") not in {"PENDING", "APPROVED"}:
        errors.append(PlanError("FINAL_APPROVAL_INVALID", "final_approval must be PENDING or APPROVED"))
    for field in ("manifest_ignore", "residual_risks", "finding_ledger", "unblock_conditions"):
        if not isinstance(metadata.get(field), list):
            errors.append(PlanError("FIELD_TYPE_INVALID", f"{field} must be a list", entity="PLAN"))

    filename_match = FILENAME_RE.match(doc.path.name)
    if not filename_match:
        errors.append(PlanError("FILENAME_INVALID", "Plan filename must be implement_YYYYMMDD_HHMMSS.md"))
    if doc.h1 != doc.path.name:
        errors.append(PlanError("H1_FILENAME_MISMATCH", "H1 must exactly match the plan filename"))
    plan_id = str(metadata.get("plan_id", ""))
    plan_id_match = PLAN_ID_RE.match(plan_id)
    if not plan_id_match:
        errors.append(PlanError("PLAN_ID_INVALID", "plan_id must be PLAN-YYYYMMDD-HHMMSS"))
    elif filename_match and filename_match.groups() != plan_id_match.groups():
        errors.append(PlanError("PLAN_ID_TIME_MISMATCH", "plan_id and filename timestamps must match"))

    try:
        top_positions = _heading_positions(doc, TOP_H2_ORDER)
        if top_positions != sorted(top_positions):
            errors.append(PlanError("SECTION_ORDER", "Required top sections are out of order"))
        final_positions = _heading_positions(doc, FINAL_H2_ORDER)
        if final_positions != sorted(final_positions):
            errors.append(PlanError("SECTION_ORDER", "Final sections are out of order"))
        if top_positions and final_positions and max(top_positions) >= min(final_positions):
            errors.append(PlanError("SECTION_ORDER", "Final sections must follow the top sections"))
    except PlanError as exc:
        errors.append(exc)

    all_ids = [block.entity_id for block in doc.blocks]
    duplicates = sorted({entity_id for entity_id in all_ids if all_ids.count(entity_id) > 1})
    for duplicate in duplicates:
        errors.append(PlanError("ID_DUPLICATE", f"Duplicate entity ID: {duplicate}", entity=duplicate))

    phases = sorted(doc.blocks_of("phase"), key=lambda block: block.heading_line)
    expected_phase_ids = [f"P{index}" for index in range(1, len(phases) + 1)]
    if [block.entity_id for block in phases] != expected_phase_ids:
        errors.append(PlanError("PHASE_SEQUENCE", "Phase IDs must be sequential from P1"))
    if not phases:
        errors.append(PlanError("PHASE_MISSING", "At least one Phase is required"))

    tasks = doc.blocks_of("task")
    tests = doc.blocks_of("test")
    qas = doc.blocks_of("qa")
    task_ids = {block.entity_id for block in tasks}
    test_ids = {block.entity_id for block in tests}
    phase_ids = {block.entity_id for block in phases}

    for block in phases:
        errors.extend(
            _require_fields(
                block.data,
                [
                    "phase_id",
                    "status",
                    "depends_on",
                    "lead_approval",
                    "lead_approval_evidence",
                    "integration_manifest",
                    "integration_journal",
                    "blocked_from",
                    "blocked_reason",
                    "unblock_conditions",
                ],
                block.entity_id,
            )
        )
        if block.data.get("phase_id") != block.entity_id:
            errors.append(PlanError("ENTITY_ID_MISMATCH", "Phase heading and phase_id differ", entity=block.entity_id))
        if block.data.get("status") not in PHASE_STATUSES:
            errors.append(PlanError("PHASE_STATUS_INVALID", f"Invalid Phase status: {block.data.get('status')}", entity=block.entity_id))
        dependencies = block.data.get("depends_on")
        if not isinstance(dependencies, list):
            errors.append(PlanError("FIELD_TYPE_INVALID", "depends_on must be a list", entity=block.entity_id))
        else:
            for dependency in dependencies:
                if dependency not in phase_ids:
                    errors.append(PlanError("DEPENDENCY_UNKNOWN", f"Unknown Phase dependency: {dependency}", entity=block.entity_id))

    for block in tasks:
        errors.extend(
            _require_fields(
                block.data,
                [
                    "task_id",
                    "status",
                    "attempt",
                    "current_run",
                    "worker_tier",
                    "assigned_model",
                    "complexity",
                    "blocked_from",
                    "blocked_reason",
                    "unblock_conditions",
                    "allowed_paths",
                    "allowed_new_paths",
                    "read_paths",
                    "dependencies",
                    "acceptance_criteria",
                    "verification_tests",
                    "rework_count",
                    "current_evidence",
                    "attempts",
                ],
                block.entity_id,
            )
        )
        if block.data.get("task_id") != block.entity_id:
            errors.append(PlanError("ENTITY_ID_MISMATCH", "Task heading and task_id differ", entity=block.entity_id))
        if block.data.get("status") not in TASK_STATUSES:
            errors.append(PlanError("TASK_STATUS_INVALID", f"Invalid task status: {block.data.get('status')}", entity=block.entity_id))
        if block.data.get("worker_tier") not in WORKER_TIERS:
            errors.append(PlanError("WORKER_TIER_INVALID", "worker_tier is invalid", entity=block.entity_id))
        if block.data.get("complexity") not in COMPLEXITIES:
            errors.append(PlanError("COMPLEXITY_INVALID", "complexity is invalid", entity=block.entity_id))
        for field in ("attempt", "rework_count"):
            if not _is_nonnegative_int(block.data.get(field)):
                errors.append(PlanError("FIELD_TYPE_INVALID", f"{field} must be a non-negative integer", entity=block.entity_id))
        for dependency in block.data.get("dependencies", []) or []:
            if dependency not in task_ids:
                errors.append(PlanError("DEPENDENCY_UNKNOWN", f"Unknown task dependency: {dependency}", entity=block.entity_id))
        for test_id in block.data.get("verification_tests", []) or []:
            if test_id not in test_ids:
                errors.append(PlanError("TEST_REFERENCE_UNKNOWN", f"Unknown test reference: {test_id}", entity=block.entity_id))
        if block.checkbox_line is not None:
            expected = block.data.get("status") == "DONE"
            actual = _checkbox_checked(doc.lines[block.checkbox_line])
            if expected != actual:
                errors.append(PlanError("CHECKBOX_STATE_MISMATCH", "Task checkbox and status differ", entity=block.entity_id))

    for block in tests:
        errors.extend(
            _require_fields(
                block.data,
                [
                    "test_id",
                    "status",
                    "attempt",
                    "current_run",
                    "blocked_from",
                    "blocked_reason",
                    "unblock_conditions",
                    "scope",
                    "for_tasks",
                    "covers_paths",
                    "kind",
                    "expected",
                    "actual",
                    "evidence",
                    "results",
                ],
                block.entity_id,
            )
        )
        if block.data.get("test_id") != block.entity_id:
            errors.append(PlanError("ENTITY_ID_MISMATCH", "Test heading and test_id differ", entity=block.entity_id))
        if block.data.get("status") not in TEST_STATUSES:
            errors.append(PlanError("TEST_STATUS_INVALID", f"Invalid test status: {block.data.get('status')}", entity=block.entity_id))
        if block.data.get("scope") not in {"TASK", "PHASE", "PLAN"}:
            errors.append(PlanError("TEST_SCOPE_INVALID", "scope must be TASK, PHASE, or PLAN", entity=block.entity_id))
        if not _is_nonnegative_int(block.data.get("attempt")):
            errors.append(PlanError("FIELD_TYPE_INVALID", "attempt must be a non-negative integer", entity=block.entity_id))
        for task_id in block.data.get("for_tasks", []) or []:
            if task_id not in task_ids:
                errors.append(PlanError("TASK_REFERENCE_UNKNOWN", f"Unknown task reference: {task_id}", entity=block.entity_id))
        if block.data.get("kind") == "command":
            errors.extend(
                _require_fields(
                    block.data,
                    [
                        "argv",
                        "cwd",
                        "timeout_seconds",
                        "expected_exit_codes",
                        "env_allowlist",
                        "network_required",
                        "command_sha256",
                    ],
                    block.entity_id,
                )
            )
        elif block.data.get("kind") == "manual":
            errors.extend(_require_fields(block.data, ["steps", "evidence_required"], block.entity_id))
        else:
            errors.append(PlanError("TEST_KIND_INVALID", "kind must be command or manual", entity=block.entity_id))
        if block.checkbox_line is not None:
            expected = block.data.get("status") == "PASS"
            actual = _checkbox_checked(doc.lines[block.checkbox_line])
            if expected != actual:
                errors.append(PlanError("CHECKBOX_STATE_MISMATCH", "Test checkbox and status differ", entity=block.entity_id))

    phase_qa_ids: set[str] = set()
    final_qa_count = 0
    for block in qas:
        errors.extend(
            _require_fields(
                block.data,
                [
                    "qa_id",
                    "status",
                    "verdict",
                    "current_attempt",
                    "current_run",
                    "blocked_from",
                    "blocked_reason",
                    "unblock_conditions",
                    "scope",
                    "required_tests",
                    "attempts",
                ],
                block.entity_id,
            )
        )
        if block.data.get("qa_id") != block.entity_id:
            errors.append(PlanError("ENTITY_ID_MISMATCH", "QA heading and qa_id differ", entity=block.entity_id))
        if block.data.get("status") not in QA_STATUSES:
            errors.append(PlanError("QA_STATUS_INVALID", f"Invalid QA status: {block.data.get('status')}", entity=block.entity_id))
        if block.data.get("verdict") not in QA_VERDICTS:
            errors.append(PlanError("QA_VERDICT_INVALID", f"Invalid QA verdict: {block.data.get('verdict')}", entity=block.entity_id))
        if not _is_nonnegative_int(block.data.get("current_attempt")):
            errors.append(PlanError("FIELD_TYPE_INVALID", "current_attempt must be a non-negative integer", entity=block.entity_id))
        for test_id in block.data.get("required_tests", []) or []:
            if test_id not in test_ids:
                errors.append(PlanError("TEST_REFERENCE_UNKNOWN", f"Unknown QA test reference: {test_id}", entity=block.entity_id))
        if block.entity_id == "QA-FINAL":
            final_qa_count += 1
            if block.phase_id is not None:
                errors.append(PlanError("QA_FINAL_LOCATION", "QA-FINAL must be outside a Phase", entity=block.entity_id))
        else:
            phase_qa_ids.add(block.phase_id or "")
        if block.checkbox_line is not None:
            expected = block.data.get("status") == "FINISHED" and block.data.get("verdict") == "PASS"
            actual = _checkbox_checked(doc.lines[block.checkbox_line])
            if expected != actual:
                errors.append(PlanError("CHECKBOX_STATE_MISMATCH", "QA checkbox and state differ", entity=block.entity_id))

    if final_qa_count != 1:
        errors.append(PlanError("QA_FINAL_COUNT", f"Exactly one QA-FINAL is required; found {final_qa_count}"))
    for phase_id in phase_ids:
        if phase_id not in phase_qa_ids:
            errors.append(PlanError("PHASE_QA_MISSING", f"Phase {phase_id} has no independent QA", entity=phase_id))

    current_phase = metadata.get("current_phase")
    if current_phase != "NONE" and current_phase not in phase_ids:
        errors.append(PlanError("CURRENT_PHASE_INVALID", f"Unknown current_phase: {current_phase}", entity="PLAN"))

    errors.extend(_validate_dependency_cycles(tasks))
    errors.extend(_validate_attempt_validities(doc))
    errors.extend(_validate_graph_and_runtime_state(doc))
    errors.extend(_validate_derived_checkboxes(doc))
    errors.extend(_validate_ledgers(doc))
    return errors


def _validate_graph_and_runtime_state(doc: PlanDocument) -> list[PlanError]:
    errors: list[PlanError] = []
    phases = sorted(doc.blocks_of("phase"), key=lambda block: block.heading_line)
    tasks = doc.blocks_of("task")
    tests = doc.blocks_of("test")
    qas = doc.blocks_of("qa")
    phase_index = {phase.entity_id: index for index, phase in enumerate(phases)}
    phase_graph = {
        phase.entity_id: list(phase.data.get("depends_on", []) or [])
        for phase in phases
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_phase(phase_id: str) -> bool:
        if phase_id in visiting:
            return True
        if phase_id in visited:
            return False
        visiting.add(phase_id)
        for dependency in phase_graph.get(phase_id, []):
            if visit_phase(dependency):
                return True
        visiting.remove(phase_id)
        visited.add(phase_id)
        return False

    if any(visit_phase(phase.entity_id) for phase in phases):
        errors.append(PlanError("DEPENDENCY_CYCLE", "Phase dependency graph contains a cycle"))

    for phase in phases:
        phase_tasks = [item for item in tasks if item.phase_id == phase.entity_id]
        phase_tests = [item for item in tests if item.phase_id == phase.entity_id]
        phase_qas = [item for item in qas if item.phase_id == phase.entity_id]
        if not phase_tasks:
            errors.append(PlanError("PHASE_TASK_MISSING", "Each Phase requires at least one DEV", entity=phase.entity_id))
        if not phase_tests:
            errors.append(PlanError("PHASE_TEST_MISSING", "Each Phase requires at least one TEST", entity=phase.entity_id))
        if len(phase_qas) != 1:
            errors.append(PlanError("PHASE_QA_COUNT", "Each Phase requires exactly one QA", entity=phase.entity_id))
        if phase_qas:
            expected_scope = {item.entity_id for item in phase_tasks}
            expected_tests = {item.entity_id for item in phase_tests}
            if set(phase_qas[0].data.get("scope", []) or []) != expected_scope:
                errors.append(PlanError("PHASE_QA_SCOPE", "Phase QA scope must enumerate its DEV IDs", entity=phase_qas[0].entity_id))
            if set(phase_qas[0].data.get("required_tests", []) or []) != expected_tests:
                errors.append(PlanError("PHASE_QA_TESTS", "Phase QA required_tests must enumerate its TEST IDs", entity=phase_qas[0].entity_id))
        if phase.data.get("status") == "QA":
            for task in phase_tasks:
                if task.data.get("status") not in {"WORKER_DONE", "DONE"}:
                    errors.append(PlanError("PHASE_STATE_INCONSISTENT", "QA Phase contains incomplete DEV", entity=phase.entity_id))
            for test in phase_tests:
                if test.data.get("status") != "PASS":
                    errors.append(PlanError("PHASE_STATE_INCONSISTENT", "QA Phase contains a non-PASS TEST", entity=phase.entity_id))
        if phase.data.get("status") == "DONE":
            if phase.data.get("lead_approval") != "APPROVED":
                errors.append(PlanError("PHASE_STATE_INCONSISTENT", "DONE Phase requires Lead approval", entity=phase.entity_id))
            errors.extend(
                PlanError(error.code, error.message, entity=phase.entity_id)
                for error in validate_evidence_shape(phase.data.get("lead_approval_evidence"))
            )
            for field in ("integration_manifest", "integration_journal"):
                errors.extend(
                    PlanError(error.code, error.message, entity=phase.entity_id)
                    for error in validate_evidence_shape(phase.data.get(field))
                )
            if any(task.data.get("status") != "DONE" for task in phase_tasks):
                errors.append(PlanError("PHASE_STATE_INCONSISTENT", "DONE Phase contains incomplete DEV", entity=phase.entity_id))
            if any(test.data.get("status") != "PASS" for test in phase_tests):
                errors.append(PlanError("PHASE_STATE_INCONSISTENT", "DONE Phase contains non-PASS TEST", entity=phase.entity_id))
            if not phase_qas or phase_qas[0].data.get("status") != "FINISHED" or phase_qas[0].data.get("verdict") != "PASS":
                errors.append(PlanError("PHASE_STATE_INCONSISTENT", "DONE Phase requires PASS QA", entity=phase.entity_id))
        for dependency_id in phase.data.get("depends_on", []) or []:
            if dependency_id in phase_index and phase_index[dependency_id] >= phase_index[phase.entity_id]:
                errors.append(PlanError("DEPENDENCY_ORDER", "Phase may only depend on an earlier Phase", entity=phase.entity_id))

    for task in tasks:
        if task.phase_id not in phase_index:
            errors.append(PlanError("ENTITY_LOCATION_INVALID", "DEV must be inside a Phase", entity=task.entity_id))
            continue
        for dependency_id in task.data.get("dependencies", []) or []:
            dependency = next((item for item in tasks if item.entity_id == dependency_id), None)
            if dependency and phase_index.get(dependency.phase_id, -1) > phase_index[task.phase_id]:
                errors.append(PlanError("DEPENDENCY_ORDER", "DEV cannot depend on a later Phase", entity=task.entity_id))
        status = task.data.get("status")
        current_run = task.data.get("current_run")
        if status in {"ASSIGNED", "IN_PROGRESS"} and not isinstance(current_run, dict):
            errors.append(PlanError("RUN_STATE_INVALID", f"{status} DEV requires current_run", entity=task.entity_id))
        if status not in {"ASSIGNED", "IN_PROGRESS", "BLOCKED"} and current_run != "NONE":
            errors.append(PlanError("RUN_STATE_INVALID", f"{status} DEV cannot have current_run", entity=task.entity_id))
        if status in {"ASSIGNED", "IN_PROGRESS", "WORKER_DONE", "DONE"}:
            if task.data.get("worker_tier") not in {"TERRA", "LUNA"}:
                errors.append(PlanError("ROUTING_STATE_INVALID", "Active/completed DEV requires a Worker tier", entity=task.entity_id))
            if not _is_nonempty_string(task.data.get("assigned_model")) or task.data.get("assigned_model") == "UNASSIGNED":
                errors.append(PlanError("ROUTING_STATE_INVALID", "Active/completed DEV requires assigned_model", entity=task.entity_id))
        if status in {"WORKER_DONE", "DONE"}:
            errors.extend(
                PlanError(error.code, error.message, entity=task.entity_id)
                for error in validate_evidence_shape(task.data.get("current_evidence"))
            )

    for test in tests:
        if test.phase_id not in phase_index:
            errors.append(PlanError("ENTITY_LOCATION_INVALID", "TEST must be inside a Phase", entity=test.entity_id))
        phase_task_ids = {item.entity_id for item in tasks if item.phase_id == test.phase_id}
        if not set(test.data.get("for_tasks", []) or []).issubset(phase_task_ids):
            errors.append(PlanError("TEST_TASK_SCOPE", "TEST may only reference DEV IDs in its Phase", entity=test.entity_id))
        status = test.data.get("status")
        current_run = test.data.get("current_run")
        if status == "RUNNING" and not isinstance(current_run, dict):
            errors.append(PlanError("RUN_STATE_INVALID", "RUNNING TEST requires current_run", entity=test.entity_id))
        if status != "RUNNING" and current_run != "NONE":
            errors.append(PlanError("RUN_STATE_INVALID", f"{status} TEST cannot have current_run", entity=test.entity_id))
        if status in {"PASS", "FAIL"}:
            results = test.data.get("results", []) or []
            if not results or results[-1].get("result") != status or results[-1].get("validity") != "VALID":
                errors.append(PlanError("TEST_RESULT_INVALID", f"{status} TEST requires a current VALID result", entity=test.entity_id))
            errors.extend(
                PlanError(error.code, error.message, entity=test.entity_id)
                for error in validate_evidence_shape(test.data.get("evidence"))
            )

    for qa in qas:
        status = qa.data.get("status")
        current_run = qa.data.get("current_run")
        if status == "RUNNING" and not isinstance(current_run, dict):
            errors.append(PlanError("RUN_STATE_INVALID", "RUNNING QA requires current_run", entity=qa.entity_id))
        if status != "RUNNING" and current_run != "NONE":
            errors.append(PlanError("RUN_STATE_INVALID", f"{status} QA cannot have current_run", entity=qa.entity_id))
        if status == "FINISHED":
            attempts = qa.data.get("attempts", []) or []
            verdict = qa.data.get("verdict")
            if not attempts or attempts[-1].get("validity") != "VALID" or attempts[-1].get("verdict") != verdict:
                errors.append(PlanError("QA_RESULT_INVALID", "FINISHED QA requires a current VALID attempt", entity=qa.entity_id))

    final_qa = next((item for item in qas if item.entity_id == "QA-FINAL"), None)
    if final_qa:
        if set(final_qa.data.get("scope", []) or []) != {phase.entity_id for phase in phases}:
            errors.append(PlanError("QA_FINAL_SCOPE", "QA-FINAL scope must enumerate every Phase", entity="QA-FINAL"))
        if set(final_qa.data.get("required_tests", []) or []) != {test.entity_id for test in tests}:
            errors.append(PlanError("QA_FINAL_TESTS", "QA-FINAL required_tests must enumerate every TEST", entity="QA-FINAL"))

    plan_status = doc.metadata.get("status")
    current_phase = doc.metadata.get("current_phase")
    if plan_status in {"DRAFT", "READY"}:
        if phases and current_phase != phases[0].entity_id:
            errors.append(PlanError("CURRENT_PHASE_INVALID", f"{plan_status} must point to P1", entity="PLAN"))
        if any(phase.data.get("status") != "PENDING" for phase in phases):
            errors.append(PlanError("PLAN_STATE_INCONSISTENT", f"{plan_status} requires all Phases PENDING", entity="PLAN"))
    elif plan_status == "IN_PROGRESS":
        phase = next((item for item in phases if item.entity_id == current_phase), None)
        if not phase or phase.data.get("status") not in {"IN_PROGRESS", "QA"}:
            errors.append(PlanError("PLAN_STATE_INCONSISTENT", "IN_PROGRESS requires an active current Phase", entity="PLAN"))
    elif plan_status == "QA":
        if current_phase != "NONE" or any(phase.data.get("status") != "DONE" for phase in phases):
            errors.append(PlanError("PLAN_STATE_INCONSISTENT", "Plan QA requires every Phase DONE and current_phase NONE", entity="PLAN"))
    elif plan_status == "COMPLETED":
        if current_phase != "NONE" or doc.metadata.get("final_approval") != "APPROVED":
            errors.append(PlanError("PLAN_STATE_INCONSISTENT", "COMPLETED requires final approval and current_phase NONE", entity="PLAN"))
        if any(phase.data.get("status") != "DONE" for phase in phases):
            errors.append(PlanError("PLAN_STATE_INCONSISTENT", "COMPLETED requires every Phase DONE", entity="PLAN"))
        if not final_qa or final_qa.data.get("status") != "FINISHED" or final_qa.data.get("verdict") != "PASS":
            errors.append(PlanError("PLAN_STATE_INCONSISTENT", "COMPLETED requires QA-FINAL PASS", entity="PLAN"))
        errors.extend(
            PlanError(error.code, error.message, entity="PLAN")
            for error in validate_evidence_shape(doc.metadata.get("final_approval_evidence"))
        )
    if plan_status == "BLOCKED":
        if doc.metadata.get("blocked_from") not in PLAN_STATUSES - {"BLOCKED"}:
            errors.append(PlanError("BLOCK_STATE_INVALID", "BLOCKED Plan requires a valid blocked_from", entity="PLAN"))
        if not _is_nonempty_string(doc.metadata.get("blocked_reason")) or not doc.metadata.get("unblock_conditions"):
            errors.append(PlanError("BLOCK_STATE_INVALID", "BLOCKED Plan requires reason and unblock conditions", entity="PLAN"))
    elif plan_status in PLAN_STATUSES:
        if doc.metadata.get("blocked_from") != "NONE":
            errors.append(PlanError("BLOCK_STATE_INVALID", "Non-BLOCKED Plan must clear blocked_from", entity="PLAN"))
    return errors


def _validate_derived_checkboxes(doc: PlanDocument) -> list[PlanError]:
    errors: list[PlanError] = []
    phase_done = {phase.entity_id: phase.data.get("status") == "DONE" for phase in doc.blocks_of("phase")}
    seen_summary: set[str] = set()
    for line in doc.lines:
        match = re.match(r"^-\s+\[[ xX]\]\s+(P[0-9]+)\s+.+완료\s*$", line)
        if not match:
            continue
        phase_id = match.group(1)
        seen_summary.add(phase_id)
        if phase_id in phase_done and _checkbox_checked(line) != phase_done[phase_id]:
            errors.append(PlanError("CHECKBOX_STATE_MISMATCH", "Phase summary checkbox and status differ", entity=phase_id))
    if seen_summary != set(phase_done):
        errors.append(PlanError("PHASE_SUMMARY_INVALID", "Phase summary must enumerate every Phase"))

    for phase_id, (start, end) in _phase_line_ranges(doc).items():
        heading = _find_heading_line(doc.headings, "완료 조건", 3, start, end)
        completion_lines = []
        if heading is not None:
            completion_lines = [
                line for line in doc.lines[heading + 1 : end] if re.match(r"^-\s+\[[ xX]\]", line)
            ]
        if len(completion_lines) != 5:
            errors.append(PlanError("PHASE_COMPLETION_INVALID", "Phase must contain five completion gates", entity=phase_id))
        for line in completion_lines:
            if _checkbox_checked(line) != phase_done.get(phase_id, False):
                errors.append(PlanError("CHECKBOX_STATE_MISMATCH", "Phase completion checkbox and status differ", entity=phase_id))

    final_start = _find_heading_line(doc.headings, "최종 승인", 2, 0, len(doc.lines))
    final_lines = []
    if final_start is not None:
        final_lines = [line for line in doc.lines[final_start + 1 :] if re.match(r"^-\s+\[[ xX]\]", line)]
    final_qa = next((item for item in doc.blocks_of("qa") if item.entity_id == "QA-FINAL"), None)
    expected = [
        bool(phase_done) and all(phase_done.values()),
        bool(final_qa and final_qa.data.get("status") == "FINISHED" and final_qa.data.get("verdict") == "PASS"),
        doc.metadata.get("final_approval") == "APPROVED",
        doc.metadata.get("final_approval") == "APPROVED",
    ]
    if len(final_lines) != 4:
        errors.append(PlanError("FINAL_CHECKLIST_INVALID", "Final approval must contain four gates"))
    else:
        for line, value in zip(final_lines, expected):
            if _checkbox_checked(line) != value:
                errors.append(PlanError("CHECKBOX_STATE_MISMATCH", "Final approval checkbox and state differ", entity="PLAN"))
    return errors


def _validate_ledgers(doc: PlanDocument) -> list[PlanError]:
    errors: list[PlanError] = []
    ledger = doc.metadata.get("finding_ledger", [])
    risks = doc.metadata.get("residual_risks", [])
    if not isinstance(ledger, list) or not isinstance(risks, list):
        return errors
    finding_refs: set[str] = set()
    for finding in ledger:
        if not isinstance(finding, dict):
            errors.append(PlanError("FINDING_INVALID", "finding_ledger entries must be mappings", entity="PLAN"))
            continue
        finding_ref = finding.get("finding_ref")
        if not _is_nonempty_string(finding_ref) or finding_ref in finding_refs:
            errors.append(PlanError("FINDING_INVALID", "finding_ref must be unique and non-empty", entity="PLAN"))
        else:
            finding_refs.add(finding_ref)
        if finding.get("severity") not in {"critical", "major", "minor", "info"}:
            errors.append(PlanError("FINDING_INVALID", "finding severity is invalid", entity="PLAN"))
        if finding.get("status") not in {"OPEN", "RESOLVED", "ACCEPTED_RISK"}:
            errors.append(PlanError("FINDING_INVALID", "finding status is invalid", entity="PLAN"))
        opened_by = finding.get("opened_by")
        if not isinstance(opened_by, dict):
            errors.append(PlanError("FINDING_INVALID", "finding opened_by is required", entity="PLAN"))
        else:
            errors.extend(
                PlanError(error.code, error.message, entity="PLAN")
                for error in validate_evidence_shape(opened_by.get("report_manifest"))
            )
        if finding.get("status") == "RESOLVED":
            resolved_by = finding.get("resolved_by")
            if not isinstance(resolved_by, dict):
                errors.append(PlanError("FINDING_INVALID", "RESOLVED finding requires resolved_by", entity="PLAN"))
            else:
                errors.extend(
                    PlanError(error.code, error.message, entity="PLAN")
                    for error in validate_evidence_shape(resolved_by.get("resolution_evidence"))
                )

    risk_ids: set[str] = set()
    for risk in risks:
        if not isinstance(risk, dict):
            errors.append(PlanError("RISK_INVALID", "residual_risks entries must be mappings", entity="PLAN"))
            continue
        risk_id = risk.get("risk_id")
        if not _is_nonempty_string(risk_id) or risk_id in risk_ids:
            errors.append(PlanError("RISK_INVALID", "risk_id must be unique and non-empty", entity="PLAN"))
        else:
            risk_ids.add(risk_id)
        if risk.get("decision") != "ACCEPTED" or risk.get("finding_ref") not in finding_refs:
            errors.append(PlanError("RISK_INVALID", "Accepted risk must reference an existing finding", entity="PLAN"))
        errors.extend(
            PlanError(error.code, error.message, entity="PLAN")
            for error in validate_evidence_shape(risk.get("approval_evidence"))
        )
        finding = next(
            (
                item
                for item in ledger
                if isinstance(item, dict) and item.get("finding_ref") == risk.get("finding_ref")
            ),
            None,
        )
        if not finding or finding.get("status") != "ACCEPTED_RISK":
            errors.append(
                PlanError(
                    "RISK_INVALID",
                    "Every residual risk must reference an ACCEPTED_RISK finding",
                    entity="PLAN",
                )
            )
    risk_findings = {
        risk.get("finding_ref")
        for risk in risks
        if isinstance(risk, dict) and risk.get("decision") == "ACCEPTED"
    }
    for finding in ledger:
        if (
            isinstance(finding, dict)
            and finding.get("status") == "ACCEPTED_RISK"
            and finding.get("finding_ref") not in risk_findings
        ):
            errors.append(
                PlanError(
                    "RISK_INVALID",
                    "ACCEPTED_RISK finding requires a matching residual_risks entry",
                    entity="PLAN",
                )
            )
    return errors


def _validate_dependency_cycles(tasks: list[EntityBlock]) -> list[PlanError]:
    graph = {block.entity_id: list(block.data.get("dependencies", []) or []) for block in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dependency in graph.get(node, []):
            if visit(dependency):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for task_id in graph:
        if visit(task_id):
            return [PlanError("DEPENDENCY_CYCLE", f"Task dependency cycle includes {task_id}", entity=task_id)]
    return []


def _validate_attempt_validities(doc: PlanDocument) -> list[PlanError]:
    errors: list[PlanError] = []
    for block in doc.blocks:
        for field in ("attempts", "results"):
            records = block.data.get(field, [])
            if not isinstance(records, list):
                errors.append(PlanError("FIELD_TYPE_INVALID", f"{field} must be a list", entity=block.entity_id))
                continue
            seen_attempts: set[int] = set()
            for record in records:
                if not isinstance(record, dict):
                    errors.append(PlanError("ATTEMPT_INVALID", f"{field} entries must be mappings", entity=block.entity_id))
                    continue
                attempt = record.get("attempt")
                if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
                    errors.append(PlanError("ATTEMPT_INVALID", "attempt must be a positive integer", entity=block.entity_id))
                elif attempt in seen_attempts:
                    errors.append(PlanError("ATTEMPT_DUPLICATE", f"Duplicate attempt {attempt}", entity=block.entity_id))
                else:
                    seen_attempts.add(attempt)
                if record.get("validity") not in VALIDITIES:
                    errors.append(PlanError("ATTEMPT_VALIDITY_INVALID", f"Invalid validity in {field}", entity=block.entity_id))
                evidence = record.get("evidence_manifest")
                evidence_errors = validate_evidence_shape(
                    evidence,
                    required=record.get("validity") != "INVALID",
                )
                errors.extend(
                    PlanError(error.code, error.message, entity=block.entity_id)
                    for error in evidence_errors
                )
                for reference_field in ("input_manifest", "contract_manifest", "runtime_attestation"):
                    if record.get(reference_field) not in (None, "NONE", "UNSET"):
                        errors.extend(
                            PlanError(error.code, error.message, entity=block.entity_id)
                            for error in validate_evidence_shape(record.get(reference_field))
                        )
    return errors


def _contains_placeholder(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(value, str) and PLACEHOLDER_RE.search(value):
        found.append(".".join(path) or "<root>")
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(_contains_placeholder(item, path + (str(key),)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_contains_placeholder(item, path + (str(index),)))
    return found


def validate_restricted_path(value: str) -> bool:
    if not isinstance(value, str) or not RESTRICTED_PATH_RE.fullmatch(value):
        return False
    if value in {".", "**"} or value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    parts = value.split("/")
    if ".." in parts or "." in parts:
        return False
    if value in {"dev-plan/**", ".git/**"} or value.startswith("dev-plan/") or value.startswith(".git/"):
        return False
    return True


def restricted_paths_overlap(left: str, right: str) -> bool:
    """Return True when two validated literal/terminal-/** matchers may intersect."""
    if left == right:
        return True
    left_prefix = left[:-3] if left.endswith("/**") else None
    right_prefix = right[:-3] if right.endswith("/**") else None
    if left_prefix is not None and (
        right == left_prefix or right.startswith(left_prefix + "/")
    ):
        return True
    if right_prefix is not None and (
        left == right_prefix or left.startswith(right_prefix + "/")
    ):
        return True
    return False


def path_sets_overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    return any(restricted_paths_overlap(a, b) for a in left for b in right)


def validate_safe_cwd(value: Any) -> bool:
    if value == ".":
        return True
    return isinstance(value, str) and validate_restricted_path(value) and not value.endswith("/**")


def validate_path_boundary(value: str, *, project_root: Path) -> bool:
    if not validate_restricted_path(value):
        return False
    relative = value[:-3] if value.endswith("/**") else value
    root = project_root.resolve()
    candidate = root / relative
    probe = candidate
    while not probe.exists() and probe != root:
        probe = probe.parent
    try:
        resolved_probe = probe.resolve()
    except (OSError, RuntimeError):
        return False
    if not resolved_probe.is_relative_to(root):
        return False
    if not candidate.exists():
        return True
    if candidate.is_symlink():
        return False
    try:
        resolved_base = candidate.resolve()
    except (OSError, RuntimeError):
        return False
    if not resolved_base.is_relative_to(root):
        return False
    if candidate.is_dir():
        checked = 0
        for directory, names, filenames in os.walk(candidate, topdown=True, followlinks=False):
            directory_path = Path(directory)
            for name in [*names, *filenames]:
                entry = directory_path / name
                if not entry.is_symlink():
                    continue
                checked += 1
                if checked > 100_000:
                    return False
                try:
                    target = entry.resolve()
                except (OSError, RuntimeError):
                    return False
                if not target.is_relative_to(resolved_base):
                    return False
    return True


def command_digest(test_data: dict[str, Any]) -> str:
    keys = [
        "kind",
        "argv",
        "cwd",
        "timeout_seconds",
        "expected_exit_codes",
        "env_allowlist",
        "network_required",
    ]
    canonical = json.dumps({key: test_data.get(key) for key in keys}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_executable(
    doc: PlanDocument,
    *,
    target_state: str | None = None,
    candidate_event: dict[str, Any] | None = None,
    check_evidence: bool = True,
) -> list[PlanError]:
    candidate = doc.clone()
    errors = validate_structural(candidate)
    if errors:
        return errors
    if candidate_event:
        try:
            apply_event(candidate, candidate_event, verify_evidence=check_evidence, candidate=True)
        except PlanError as exc:
            return [exc]
    effective_state = target_state or str(candidate.metadata.get("status"))
    if target_state and candidate.metadata.get("status") != target_state:
        errors.append(PlanError("TARGET_STATE_MISMATCH", f"Candidate event produced {candidate.metadata.get('status')}, expected {target_state}"))
    if not target_state and effective_state not in {"READY", "IN_PROGRESS", "QA"}:
        errors.append(PlanError("PLAN_STATE_NOT_EXECUTABLE", f"Plan status {effective_state} is not executable"))

    for path in _contains_placeholder(candidate.metadata):
        if effective_state == "READY" and path in {"execution_baseline", "execution_evidence"}:
            continue
        errors.append(PlanError("PLACEHOLDER_FOUND", f"Placeholder remains in plan metadata: {path}", entity="PLAN"))
    for block in candidate.blocks:
        for path in _contains_placeholder(block.data):
            errors.append(PlanError("PLACEHOLDER_FOUND", f"Placeholder remains: {path}", entity=block.entity_id))

    project_root = project_root_for(candidate.path)
    if effective_state in {"READY", "IN_PROGRESS", "QA"}:
        if candidate.metadata.get("planning_revision") in {"UNSET", "NONE", None}:
            errors.append(PlanError("PLANNING_REVISION_MISSING", "planning_revision is required"))
        if check_evidence:
            errors.extend(
                validate_evidence_manifest_reference(
                    candidate.metadata.get("planning_evidence"),
                    project_root=project_root,
                    expected_plan_id=str(candidate.metadata.get("plan_id")),
                    expected_entity_id="PLAN",
                    expected_stage="BASELINE",
                    expected_attempt=0,
                    check_current_state=effective_state == "READY",
                )
            )
            errors.extend(
                validate_revision_binding(
                    candidate.metadata.get("planning_revision"),
                    evidence_manifest_ref=candidate.metadata.get("planning_evidence"),
                    project_root=project_root,
                    check_current_revision=effective_state == "READY",
                )
            )
    if effective_state in {"IN_PROGRESS", "QA"}:
        if candidate.metadata.get("execution_baseline") in {"UNSET", "NONE", None}:
            errors.append(PlanError("EXECUTION_BASELINE_MISSING", "execution_baseline is required"))
        if check_evidence:
            errors.extend(
                validate_evidence_manifest_reference(
                    candidate.metadata.get("execution_evidence"),
                    project_root=project_root,
                    expected_plan_id=str(candidate.metadata.get("plan_id")),
                    expected_entity_id="PLAN",
                    expected_stage="BASELINE",
                    expected_attempt=0,
                    check_current_state=False,
                )
            )
            errors.extend(
                validate_revision_binding(
                    candidate.metadata.get("execution_baseline"),
                    evidence_manifest_ref=candidate.metadata.get("execution_evidence"),
                    project_root=project_root,
                    check_current_revision=False,
                )
            )

    for block in candidate.blocks_of("task"):
        for field in ("allowed_paths", "allowed_new_paths", "read_paths"):
            values = block.data.get(field)
            if not isinstance(values, list) or not values:
                errors.append(PlanError("PATHS_MISSING", f"{field} must be a non-empty list", entity=block.entity_id))
                continue
            for value in values:
                if not validate_restricted_path(value):
                    errors.append(PlanError("PATH_INVALID", f"Invalid restricted path: {value}", entity=block.entity_id))
                elif not validate_path_boundary(value, project_root=project_root):
                    errors.append(PlanError("PATH_BOUNDARY_INVALID", f"Path resolves outside its allowed boundary: {value}", entity=block.entity_id))
        if not block.data.get("acceptance_criteria"):
            errors.append(PlanError("ACCEPTANCE_CRITERIA_MISSING", "acceptance_criteria is required", entity=block.entity_id))
        if not block.data.get("verification_tests"):
            errors.append(PlanError("VERIFICATION_MISSING", "verification_tests is required", entity=block.entity_id))

    for block in candidate.blocks_of("test"):
        covers_paths = block.data.get("covers_paths")
        if not isinstance(covers_paths, list) or not covers_paths:
            errors.append(PlanError("PATHS_MISSING", "covers_paths must be a non-empty list", entity=block.entity_id))
            covers_paths = []
        for value in covers_paths:
            if not validate_restricted_path(value):
                errors.append(PlanError("PATH_INVALID", f"Invalid covers_paths value: {value}", entity=block.entity_id))
            elif not validate_path_boundary(value, project_root=project_root):
                errors.append(PlanError("PATH_BOUNDARY_INVALID", f"covers_paths escapes its boundary: {value}", entity=block.entity_id))
        if block.data.get("kind") == "command":
            argv = block.data.get("argv")
            if not isinstance(argv, list) or not argv or not all(
                isinstance(item, str)
                and bool(item)
                and not any(ord(character) < 32 for character in item)
                for item in argv
            ):
                errors.append(PlanError("ARGV_INVALID", "argv must be a non-empty string list", entity=block.entity_id))
            elif _is_inline_interpreter(argv):
                errors.append(PlanError("INLINE_COMMAND_FORBIDDEN", "Inline shell/interpreter commands are forbidden", entity=block.entity_id))
            if not validate_safe_cwd(block.data.get("cwd")):
                errors.append(PlanError("CWD_INVALID", "cwd must be '.' or a literal project-relative directory", entity=block.entity_id))
            elif block.data.get("cwd") != "." and not validate_path_boundary(
                str(block.data.get("cwd")),
                project_root=project_root,
            ):
                errors.append(PlanError("CWD_INVALID", "cwd resolves outside the project boundary", entity=block.entity_id))
            if command_digest(block.data) != str(block.data.get("command_sha256")):
                errors.append(PlanError("COMMAND_DIGEST_MISMATCH", "command_sha256 does not match canonical command", entity=block.entity_id))
            if not isinstance(block.data.get("timeout_seconds"), int) or int(block.data.get("timeout_seconds", 0)) <= 0:
                errors.append(PlanError("TIMEOUT_INVALID", "timeout_seconds must be positive", entity=block.entity_id))
            exit_codes = block.data.get("expected_exit_codes")
            if not isinstance(exit_codes, list) or not exit_codes or not all(
                isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 255 for item in exit_codes
            ):
                errors.append(PlanError("EXIT_CODES_INVALID", "expected_exit_codes must contain integers from 0 to 255", entity=block.entity_id))
            env_allowlist = block.data.get("env_allowlist")
            if not isinstance(env_allowlist, list) or not all(
                isinstance(item, str) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", item) for item in env_allowlist
            ):
                errors.append(PlanError("ENV_ALLOWLIST_INVALID", "env_allowlist contains an invalid environment name", entity=block.entity_id))
            elif any(re.search(r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)", item) for item in env_allowlist):
                errors.append(PlanError("SECRET_ENV_FORBIDDEN", "env_allowlist may not expose secret-like variables", entity=block.entity_id))
            if not isinstance(block.data.get("network_required"), bool):
                errors.append(PlanError("NETWORK_FLAG_INVALID", "network_required must be boolean", entity=block.entity_id))
        else:
            steps = block.data.get("steps")
            evidence_required = block.data.get("evidence_required")
            if not isinstance(steps, list) or not steps or not all(
                isinstance(item, str) and len(item.strip()) >= 8 and item.strip() not in {"확인한다.", "검증한다."}
                for item in steps
            ):
                errors.append(PlanError("MANUAL_STEPS_INVALID", "manual TEST requires reproducible non-empty steps", entity=block.entity_id))
            if not isinstance(evidence_required, list) or not evidence_required or not all(
                _is_nonempty_string(item) for item in evidence_required
            ):
                errors.append(PlanError("MANUAL_EVIDENCE_INVALID", "manual TEST requires evidence_required", entity=block.entity_id))

    final_qa = candidate.entity("QA-FINAL")
    phase_ids = {block.entity_id for block in candidate.blocks_of("phase")}
    test_ids = {block.entity_id for block in candidate.blocks_of("test")}
    if set(final_qa.data.get("scope", []) or []) != phase_ids:
        errors.append(PlanError("QA_FINAL_SCOPE", "QA-FINAL scope must enumerate every Phase", entity="QA-FINAL"))
    if not set(final_qa.data.get("required_tests", []) or []).issubset(test_ids):
        errors.append(PlanError("QA_FINAL_TESTS", "QA-FINAL required_tests contains unknown IDs", entity="QA-FINAL"))

    return errors


def _is_inline_interpreter(argv: list[str]) -> bool:
    program = Path(argv[0]).name.lower()
    args = [item.lower() for item in argv[1:]]
    if program == "env":
        index = 0
        while index < len(args):
            item = args[index]
            if item in {"-s", "--split-string"}:
                return True
            if item in {"-u", "--unset"}:
                index += 2
                continue
            if item.startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[index + 1]):
                index += 1
                continue
            return _is_inline_interpreter(argv[index + 1 :])
        return False
    if program in {"sh", "bash", "zsh", "dash", "ksh"} and any(
        item == "-c" or (item.startswith("-") and "c" in item[1:]) for item in args
    ):
        return True
    if program == "cmd" and any(item == "/c" for item in args):
        return True
    if program in {"powershell", "pwsh"} and any(
        item in {"-c", "-command", "-encodedcommand", "-ec"} for item in args
    ):
        return True
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", program) and "-c" in args:
        return True
    if re.fullmatch(r"(?:node|nodejs)(?:\d+(?:\.\d+)*)?", program) and any(
        item in {"-e", "--eval", "-p", "--print"} for item in args
    ):
        return True
    if re.fullmatch(r"(?:ruby|perl)(?:\d+(?:\.\d+)*)?", program) and "-e" in args:
        return True
    return False


def make_error_report(errors: list[PlanError], *, executable: bool = False) -> dict[str, Any]:
    return {
        "valid": not errors,
        "status": "PLAN_VALID" if not errors else ("PLAN_NOT_EXECUTABLE" if executable else "PLAN_INVALID"),
        "errors": [error.as_dict() for error in errors],
    }


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(spec)
    phases = value.get("phases")
    if not isinstance(phases, list) or not phases:
        phases = [
            {
                "name": "TODO",
                "goal": "TODO 이 Phase의 목표를 구체화한다.",
                "tasks": [
                    {
                        "title": "TODO 구현 태스크",
                        "objective": "TODO 구현 목표를 구체화한다.",
                        "allowed_paths": ["TODO"],
                        "allowed_new_paths": ["TODO"],
                        "read_paths": ["TODO"],
                        "dependencies": [],
                        "complexity": "ROUTINE",
                        "acceptance_criteria": ["TODO 완료 기준을 구체화한다."],
                        "tests": [
                            {
                                "title": "TODO 검증",
                                "kind": "manual",
                                "steps": ["TODO 재현 가능한 검증 절차를 작성한다."],
                                "expected": "TODO 기대 결과를 작성한다.",
                                "evidence_required": ["TODO"],
                            }
                        ],
                    }
                ],
            }
        ]
    normalized_phases: list[dict[str, Any]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            raise PlanError("SPEC_INVALID", "Each Phase spec must be a mapping")
        normalized_phase = copy.deepcopy(phase)
        tasks = normalized_phase.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            normalized_phase["tasks"] = [
                {
                    "title": "TODO 구현 태스크",
                    "objective": "TODO 구현 목표를 구체화한다.",
                    "allowed_paths": ["TODO"],
                    "allowed_new_paths": ["TODO"],
                    "read_paths": ["TODO"],
                    "dependencies": [],
                    "complexity": "ROUTINE",
                    "acceptance_criteria": ["TODO 완료 기준을 구체화한다."],
                    "tests": [
                        {
                            "title": "TODO 검증",
                            "kind": "manual",
                            "steps": ["TODO 재현 가능한 검증 절차를 작성한다."],
                            "expected": "TODO 기대 결과를 작성한다.",
                            "evidence_required": ["TODO"],
                        }
                    ],
                }
            ]
        normalized_phases.append(normalized_phase)
    value["phases"] = normalized_phases
    value.setdefault("purpose", "TODO 이번 개발의 목적을 명확하게 적는다.")
    value.setdefault("scope", ["TODO 이번 개발 범위를 구체화한다."])
    value.setdefault("excludes", ["문서에 없는 신규 기능과 무관한 리팩터링"])
    value.setdefault("references", ["없음"])
    return value


def build_plan_content(
    *,
    filename: str,
    plan_id: str,
    created_at: str,
    spec: dict[str, Any],
    lead_model: str,
    qa_model: str,
    isolation_mode: str,
) -> str:
    spec = normalize_spec(spec)
    phase_models: list[dict[str, Any]] = []
    task_counter = 100
    test_counter = 100
    qa_counter = 100
    all_test_ids: list[str] = []
    for phase_index, phase_spec in enumerate(spec["phases"], start=1):
        phase_id = f"P{phase_index}"
        tasks: list[dict[str, Any]] = []
        tests: list[dict[str, Any]] = []
        for raw_task in phase_spec.get("tasks", []):
            task_counter += 1
            task_id = f"DEV-{task_counter}"
            test_ids: list[str] = []
            for raw_test in raw_task.get("tests", []):
                test_counter += 1
                test_id = f"TEST-{test_counter}"
                test_data: dict[str, Any] = {
                    "test_id": test_id,
                    "status": "PENDING",
                    "attempt": 0,
                    "current_run": "NONE",
                    "blocked_from": "NONE",
                    "blocked_reason": "NONE",
                    "unblock_conditions": [],
                    "scope": raw_test.get("scope", "TASK"),
                    "for_tasks": [task_id],
                    "covers_paths": list(raw_test.get("covers_paths", raw_task.get("read_paths", ["TODO"]))),
                    "kind": raw_test.get("kind", "manual"),
                }
                if test_data["kind"] == "command":
                    test_data.update(
                        {
                            "argv": list(raw_test.get("argv", [])),
                            "cwd": raw_test.get("cwd", "."),
                            "timeout_seconds": int(raw_test.get("timeout_seconds", 300)),
                            "expected_exit_codes": list(raw_test.get("expected_exit_codes", [0])),
                            "env_allowlist": list(raw_test.get("env_allowlist", ["PATH", "LANG", "LC_ALL", "TMPDIR"])),
                            "network_required": bool(raw_test.get("network_required", False)),
                        }
                    )
                    test_data["command_sha256"] = command_digest(test_data)
                else:
                    test_data.update(
                        {
                            "steps": list(raw_test.get("steps", ["TODO 재현 가능한 검증 절차를 작성한다."])),
                            "evidence_required": list(raw_test.get("evidence_required", ["TODO"])),
                        }
                    )
                test_data.update(
                    {
                        "expected": raw_test.get("expected", "TODO 기대 결과를 작성한다."),
                        "actual": "NOT_RUN",
                        "evidence": "NONE",
                        "results": [],
                    }
                )
                tests.append({"id": test_id, "title": raw_test.get("title", test_id), "data": test_data})
                test_ids.append(test_id)
                all_test_ids.append(test_id)
            task_data = {
                "task_id": task_id,
                "status": "PENDING",
                "attempt": 0,
                "current_run": "NONE",
                "worker_tier": "UNASSIGNED",
                "assigned_model": "UNASSIGNED",
                "complexity": raw_task.get("complexity", "ROUTINE"),
                "blocked_from": "NONE",
                "blocked_reason": "NONE",
                "unblock_conditions": [],
                "allowed_paths": list(raw_task.get("allowed_paths", ["TODO"])),
                "allowed_new_paths": list(raw_task.get("allowed_new_paths", raw_task.get("allowed_paths", ["TODO"]))),
                "read_paths": list(raw_task.get("read_paths", raw_task.get("allowed_paths", ["TODO"]))),
                "dependencies": list(raw_task.get("dependencies", [])),
                "acceptance_criteria": list(raw_task.get("acceptance_criteria", ["TODO 완료 기준을 구체화한다."])),
                "verification_tests": test_ids,
                "rework_count": 0,
                "current_evidence": "NONE",
                "attempts": [],
            }
            tasks.append(
                {
                    "id": task_id,
                    "title": raw_task.get("title", task_id),
                    "objective": raw_task.get("objective", "TODO 구현 목표를 구체화한다."),
                    "data": task_data,
                }
            )
        qa_counter += 1
        phase_models.append(
            {
                "id": phase_id,
                "name": phase_spec.get("name", phase_id),
                "goal": phase_spec.get("goal", "TODO 이 Phase의 목표를 구체화한다."),
                "data": {
                    "phase_id": phase_id,
                    "status": "PENDING",
                    "depends_on": [] if phase_index == 1 else [f"P{phase_index - 1}"],
                    "lead_approval": "PENDING",
                    "lead_approval_evidence": "NONE",
                    "integration_manifest": "NONE",
                    "integration_journal": "NONE",
                    "blocked_from": "NONE",
                    "blocked_reason": "NONE",
                    "unblock_conditions": [],
                },
                "tasks": tasks,
                "tests": tests,
                "qa_id": f"QA-{qa_counter}",
            }
        )

    metadata = {
        "schema": SCHEMA,
        "plan_id": plan_id,
        "status": "DRAFT",
        "current_phase": "P1",
        "document_version": 0,
        "created_at": created_at,
        "updated_at": created_at,
        "lead_model": lead_model,
        "worker_routing": "automatic",
        "isolation_mode": isolation_mode,
        "qa_model": qa_model,
        "max_rework": int(spec.get("max_rework", 2)),
        "qa_timeout_seconds": int(spec.get("qa_timeout_seconds", 1800)),
        "max_log_bytes": int(spec.get("max_log_bytes", 10_485_760)),
        "manifest_ignore": list(WORKSPACE_DEFAULT_IGNORES),
        "planning_revision": "UNSET",
        "planning_evidence": "NONE",
        "execution_baseline": "UNSET",
        "execution_evidence": "NONE",
        "final_approval": "PENDING",
        "final_approval_evidence": "NONE",
        "last_resolution_evidence": "NONE",
        "residual_risks": [],
        "finding_ledger": [],
        "blocked_from": "NONE",
        "blocked_reason": "NONE",
        "unblock_conditions": [],
    }
    if spec.get("upgrade_source") is not None:
        metadata["upgrade_source"] = copy.deepcopy(spec["upgrade_source"])

    lines: list[str] = ["---", dump_yaml(metadata), "---", f"# {filename}", "", f"작성 일시: `{created_at}`", ""]
    lines.extend(["## 개발 목적", str(spec["purpose"]), "", "## 개발 범위"])
    lines.extend(f"- {item}" for item in _as_list(spec["scope"]))
    lines.extend(["", "## 제외 범위"])
    lines.extend(f"- {item}" for item in _as_list(spec["excludes"]))
    lines.extend(["", "## 참조 문서"])
    lines.extend(f"- {item}" for item in _as_list(spec["references"]))
    lines.extend(
        [
            "",
            "## 공통 진행 규칙",
            "- 각 Phase는 앞선 Phase 승인 후에만 시작한다.",
            "- Worker와 QA는 계획 문서를 수정하지 않는다.",
            "- 문서에 없는 범위 확장은 새 계획으로 분리한다.",
            "- Independent QA PASS 전 완료 처리하지 않는다.",
            "",
            "## Phase 상태 요약",
        ]
    )
    lines.extend(f"- [ ] {phase['id']} {phase['name']} 완료" for phase in phase_models)
    lines.extend(
        [
            "",
            "## QA 관점",
            "- 실패 케이스와 경계값을 검토한다.",
            "- 계획 밖 변경, 회귀, 보안·성능·운영 위험을 검토한다.",
            "",
        ]
    )

    for phase in phase_models:
        lines.extend(
            [
                f"## Phase {phase['id'][1:]}. {phase['name']}",
                "",
                "```yaml",
                dump_yaml(phase["data"]),
                "```",
                "",
                "### 목표",
                f"- {phase['goal']}",
                "",
                "### 구현 태스크",
                "",
            ]
        )
        for task in phase["tasks"]:
            lines.extend(
                [
                    f"#### {task['id']} {task['title']}",
                    "",
                    "```yaml",
                    dump_yaml(task["data"]),
                    "```",
                    "",
                    "- [ ] 완료",
                    f"- 목표: {task['objective']}",
                    "",
                ]
            )
        lines.extend(["### 자체 테스트", ""])
        for test in phase["tests"]:
            lines.extend(
                [
                    f"#### {test['id']} {test['title']}",
                    "",
                    "```yaml",
                    dump_yaml(test["data"]),
                    "```",
                    "",
                    "- [ ] 완료",
                    "",
                ]
            )
        lines.extend(
            [
                "### 이슈 및 수정",
                "- 발견 이슈 없음",
                "",
                "### 독립 QA",
                "",
                f"#### {phase['qa_id']} {phase['id']} Independent Sol QA",
                "",
                "```yaml",
                dump_yaml(
                    {
                        "qa_id": phase["qa_id"],
                        "status": "PENDING",
                        "verdict": "PENDING",
                        "current_attempt": 0,
                        "current_run": "NONE",
                        "blocked_from": "NONE",
                        "blocked_reason": "NONE",
                        "unblock_conditions": [],
                        "scope": [task["id"] for task in phase["tasks"]],
                        "required_tests": [test["id"] for test in phase["tests"]],
                        "attempts": [],
                    }
                ),
                "```",
                "",
                "- [ ] 완료",
                "",
                "### 완료 조건",
                "- [ ] 모든 구현 태스크 완료",
                "- [ ] 모든 자체 테스트 통과",
                "- [ ] Independent QA Sol PASS",
                "- [ ] 발견 이슈 해결",
                "- [ ] Lead Sol Phase 승인",
                "",
            ]
        )

    lines.extend(
        [
            "## 최종 통합 QA",
            "",
            "#### QA-FINAL 전체 통합 검증",
            "",
            "```yaml",
            dump_yaml(
                {
                    "qa_id": "QA-FINAL",
                    "status": "PENDING",
                    "verdict": "PENDING",
                    "current_attempt": 0,
                    "current_run": "NONE",
                    "blocked_from": "NONE",
                    "blocked_reason": "NONE",
                    "unblock_conditions": [],
                    "scope": [phase["id"] for phase in phase_models],
                    "required_tests": all_test_ids,
                    "attempts": [],
                }
            ),
            "```",
            "",
            "- [ ] 완료",
            "",
            "## 최종 승인",
            "",
            "- [ ] 모든 Phase 완료",
            "- [ ] 최종 통합 QA PASS",
            "- [ ] 잔여 리스크 기록",
            "- [ ] Lead Sol 최종 승인",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def read_spec(path: str | Path) -> dict[str, Any]:
    spec_path = Path(path)
    text = spec_path.read_text(encoding="utf-8")
    if spec_path.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        value = load_yaml(text, source=str(spec_path))
    if not isinstance(value, dict):
        raise PlanError("SPEC_INVALID", "Plan spec must be an object")
    return value


def event_name_and_payload(event: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name = event.get("event")
    if not isinstance(name, str) or not name:
        raise PlanError("EVENT_PAYLOAD_INVALID", "Event payload requires an event name")
    payload = event.get("payload")
    if payload is None:
        payload = {key: value for key, value in event.items() if key != "event"}
    if not isinstance(payload, dict):
        raise PlanError("EVENT_PAYLOAD_INVALID", "event payload must be a mapping")
    return name, payload


def apply_event(
    doc: PlanDocument,
    event: dict[str, Any],
    *,
    verify_evidence: bool = True,
    candidate: bool = False,
) -> None:
    """Apply an event transactionally to an in-memory PlanDocument.

    Every guard and evidence check runs against a deep clone. The caller-visible
    document is updated only after the complete event succeeds, so a rejected
    event cannot leak partial status, evidence, or checkbox mutations.
    """

    staged = doc.clone()
    _apply_event_in_place(
        staged,
        event,
        verify_evidence=verify_evidence,
        candidate=candidate,
    )
    doc.metadata.clear()
    doc.metadata.update(copy.deepcopy(staged.metadata))
    staged_blocks = {block.entity_id: block for block in staged.blocks}
    for block in doc.blocks:
        staged_block = staged_blocks[block.entity_id]
        block.data.clear()
        block.data.update(copy.deepcopy(staged_block.data))


def _apply_event_in_place(
    doc: PlanDocument,
    event: dict[str, Any],
    *,
    verify_evidence: bool = True,
    candidate: bool = False,
) -> None:
    name, payload = event_name_and_payload(event)
    root = project_root_for(doc.path)

    def require_entity(entity_id: str) -> EntityBlock:
        return doc.entity(entity_id)

    def require_status(block: EntityBlock, allowed: set[str]) -> None:
        if block.data.get("status") not in allowed:
            raise PlanError(
                "EVENT_FROM_MISMATCH",
                f"{name} requires {block.entity_id} status in {sorted(allowed)}, got {block.data.get('status')}",
                entity=block.entity_id,
            )

    def require_plan_status(allowed: set[str]) -> None:
        if doc.metadata.get("status") not in allowed:
            raise PlanError(
                "EVENT_FROM_MISMATCH",
                f"{name} requires Plan status in {sorted(allowed)}, got {doc.metadata.get('status')}",
                entity="PLAN",
            )

    def require_value(value: Any, field: str) -> Any:
        if value in (None, "", "NONE", "UNSET", "UNASSIGNED"):
            raise PlanError("EVENT_PAYLOAD_INVALID", f"{field} is required")
        return value

    def require_active_phase(block: EntityBlock) -> EntityBlock:
        if not block.phase_id:
            raise PlanError("EVENT_PAYLOAD_INVALID", f"{block.entity_id} is not inside a Phase")
        phase = require_entity(block.phase_id)
        require_status(phase, {"IN_PROGRESS"})
        if doc.metadata.get("current_phase") != phase.entity_id:
            raise PlanError("GUARD_FAILED", f"{phase.entity_id} is not the current Phase")
        return phase

    def checked_ref(value: Any) -> Any:
        shape_errors = validate_evidence_shape(value)
        if shape_errors:
            raise shape_errors[0]
        if verify_evidence:
            errors = validate_evidence_reference(value, project_root=root)
            if errors:
                raise errors[0]
        return copy.deepcopy(value)

    def checked_attestation(
        value: Any,
        *,
        agent_id: str,
        role: str,
        model: str,
        tier: str | None = None,
    ) -> tuple[Any, dict[str, Any] | None]:
        reference = checked_ref(value)
        if not verify_evidence:
            return reference, None
        attestation, errors = validate_runtime_attestation_reference(
            reference,
            project_root=root,
            expected_agent_id=agent_id,
            expected_role=role,
            expected_model=model,
            expected_tier=tier,
        )
        if errors:
            raise errors[0]
        return reference, attestation

    def checked_approval(
        value: Any,
        *,
        kind: str,
        entity_id: str,
        approver_role: str,
    ) -> Any:
        reference = checked_ref(value)
        if verify_evidence:
            _, errors = validate_approval_evidence_reference(
                reference,
                project_root=root,
                expected_plan_id=str(doc.metadata.get("plan_id")),
                expected_kind=kind,
                expected_entity_id=entity_id,
                expected_approver_role=approver_role,
            )
            if errors:
                raise errors[0]
        return reference

    def checked_manifest(
        value: Any,
        *,
        entity_id: str,
        stage: str,
        attempt: int,
        expected_input_state_id: Any = None,
        expected_output_state_id: Any = None,
        expected_input_manifest: Any = None,
        expected_workspace_root: str | None = None,
        expected_workspace_id: str | None = None,
    ) -> Any:
        reference = checked_ref(value)
        if verify_evidence:
            errors = validate_evidence_manifest_reference(
                reference,
                project_root=root,
                expected_plan_id=str(doc.metadata.get("plan_id")),
                expected_entity_id=entity_id,
                expected_stage=stage,
                expected_attempt=attempt,
                check_current_state=stage == "BASELINE",
                expected_workspace_root=expected_workspace_root,
                expected_workspace_id=expected_workspace_id,
                require_disposable_workspace=(
                    doc.metadata.get("isolation_mode") == "MANIFEST_GUARDED"
                    and stage in {"INPUT", "RESULT"}
                ),
            )
            if errors:
                raise errors[0]
            manifest_path = (root / str(reference["path"])).resolve()
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = (
                json.loads(manifest_text)
                if manifest_path.suffix.lower() == ".json"
                else load_yaml(manifest_text, source=str(manifest_path))
            )
            if (
                expected_input_state_id is not None
                and manifest.get("input_state_id") != expected_input_state_id
            ):
                raise PlanError("EVIDENCE_STATE_MISMATCH", "Manifest input_state_id differs from event state")
            if (
                expected_output_state_id is not None
                and manifest.get("output_state_id") != expected_output_state_id
            ):
                raise PlanError("EVIDENCE_STATE_MISMATCH", "Manifest output_state_id differs from event state")
            if (
                expected_input_manifest is not None
                and manifest.get("input_manifest") != expected_input_manifest
            ):
                raise PlanError("EVIDENCE_STATE_MISMATCH", "RESULT input_manifest differs from current INPUT")
        return reference

    def require_disposable_workspace(workspace_root: str, workspace_id: str) -> None:
        if not verify_evidence or doc.metadata.get("isolation_mode") != "MANIFEST_GUARDED":
            return
        identity_errors = validate_workspace_identity(
            workspace_root,
            workspace_id,
            project_root=root,
            require_disposable=True,
        )
        if identity_errors:
            raise identity_errors[0]

    def load_evidence_manifest(reference: Any) -> dict[str, Any]:
        if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
            raise PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence manifest reference is invalid")
        path = (root / reference["path"]).resolve()
        if not path.is_relative_to((root / "dev-plan" / "evidence").resolve()):
            raise PlanError("EVIDENCE_PATH_INVALID", "Evidence manifest escapes dev-plan/evidence/")
        try:
            text = path.read_text(encoding="utf-8")
            value = (
                json.loads(text)
                if path.suffix.lower() == ".json"
                else load_yaml(text, source=str(path))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PlanError("EVIDENCE_MANIFEST_INVALID", str(exc)) from exc
        if not isinstance(value, dict):
            raise PlanError("EVIDENCE_MANIFEST_INVALID", "Evidence manifest must be a mapping")
        return value

    def workspace_inventory_for_role(
        manifest_reference: Any,
        role: str,
    ) -> dict[str, dict[str, Any]]:
        manifest = load_evidence_manifest(manifest_reference)
        entry = next(
            (
                item
                for item in manifest.get("files", []) or []
                if isinstance(item, dict) and item.get("role") == role
            ),
            None,
        )
        if not entry or not isinstance(entry.get("path"), str):
            raise PlanError(
                "EVIDENCE_MANIFEST_INVALID",
                f"Evidence manifest has no {role} workspace artifact",
            )
        workspace_path = (root / entry["path"]).resolve()
        try:
            workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PlanError("EVIDENCE_MANIFEST_INVALID", str(exc)) from exc
        files = workspace.get("files")
        if workspace.get("schema") != "codex-workspace-manifest/v1" or not isinstance(files, list):
            raise PlanError("EVIDENCE_MANIFEST_INVALID", f"{role} workspace manifest is invalid")
        return {
            str(item["path"]): item
            for item in files
            if isinstance(item, dict) and _is_nonempty_string(item.get("path"))
        }

    def state_reaches(start: Any, target: Any) -> bool:
        if start == target:
            return True
        edges = [
            (attempt.get("input_state_id"), attempt.get("output_state_id"))
            for task in doc.blocks_of("task")
            for attempt in (task.data.get("attempts", []) or [])
            if (
                attempt.get("validity") == "VALID"
                and _is_nonempty_string(attempt.get("input_state_id"))
                and _is_nonempty_string(attempt.get("output_state_id"))
            )
        ]
        frontier = [start]
        visited: set[Any] = set()
        while frontier:
            current_state = frontier.pop()
            if current_state in visited:
                continue
            visited.add(current_state)
            for before, after in edges:
                if before == current_state:
                    if after == target:
                        return True
                    frontier.append(after)
        return False

    def path_matches_restricted(path: str, pattern: str) -> bool:
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            return path == prefix or path.startswith(prefix + "/")
        return path == pattern

    def verify_phase_aggregate_state(
        phase_id: str,
        *,
        aggregate_state_id: Any,
        aggregate_input_manifest: Any,
    ) -> None:
        aggregate_inventory: dict[str, dict[str, Any]] | None = None
        for task in [item for item in doc.blocks_of("task") if item.phase_id == phase_id]:
            attempts = task.data.get("attempts", []) or []
            current_attempt = int(task.data.get("attempt", 0))
            attempt = next(
                (
                    item
                    for item in reversed(attempts)
                    if int(item.get("attempt", -1)) == current_attempt
                    and item.get("validity") == "VALID"
                ),
                None,
            )
            if attempt is None:
                raise PlanError(
                    "GUARD_FAILED",
                    f"{task.entity_id} has no current VALID Worker attempt",
                    entity=phase_id,
                )
            output_state_id = attempt.get("output_state_id")
            if state_reaches(output_state_id, aggregate_state_id):
                continue
            if not verify_evidence:
                raise PlanError(
                    "EVIDENCE_STATE_MISMATCH",
                    f"{task.entity_id} output does not reach the Phase aggregate state",
                    entity=phase_id,
                )
            if aggregate_inventory is None:
                aggregate_inventory = workspace_inventory_for_role(
                    aggregate_input_manifest,
                    "workspace_manifest",
                )
            worker_inventory = workspace_inventory_for_role(
                attempt.get("evidence_manifest"),
                "post_state",
            )
            allowed = [
                *list(task.data.get("allowed_paths", []) or []),
                *list(task.data.get("allowed_new_paths", []) or []),
            ]
            scoped_paths = {
                path
                for path in set(worker_inventory) | set(aggregate_inventory)
                if any(path_matches_restricted(path, pattern) for pattern in allowed)
            }
            if any(worker_inventory.get(path) != aggregate_inventory.get(path) for path in scoped_paths):
                raise PlanError(
                    "EVIDENCE_STATE_MISMATCH",
                    f"Phase aggregate does not preserve {task.entity_id} output on its owned paths",
                    entity=phase_id,
                )

    def reverify_attempt(record: dict[str, Any], entity: EntityBlock) -> None:
        attempt = int(record.get("attempt", -1))
        if attempt < 0:
            raise PlanError("EVIDENCE_MANIFEST_INVALID", "Attempt record has no valid attempt number")
        if entity.kind in {"task", "qa"}:
            require_disposable_workspace(
                str(record.get("workspace_root", "")),
                str(record.get("workspace_id", "")),
            )
        input_ref = record.get("input_manifest", record.get("contract_manifest"))
        input_state = record.get("tested_state_id", record.get("input_state_id"))
        output_state = record.get("tested_state_id", record.get("output_state_id"))
        if input_ref not in (None, "NONE", "UNSET"):
            checked_manifest(
                input_ref,
                entity_id=entity.entity_id,
                stage="INPUT",
                attempt=attempt,
                expected_input_state_id=input_state,
                expected_workspace_root=(
                    str(record.get("workspace_root"))
                    if _is_nonempty_string(record.get("workspace_root"))
                    else None
                ),
                expected_workspace_id=(
                    str(record.get("workspace_id"))
                    if _is_nonempty_string(record.get("workspace_id"))
                    else None
                ),
            )
        if record.get("evidence_manifest") not in (None, "NONE", "UNSET"):
            checked_manifest(
                record["evidence_manifest"],
                entity_id=entity.entity_id,
                stage="RESULT",
                attempt=attempt,
                expected_input_state_id=input_state,
                expected_output_state_id=output_state,
                expected_input_manifest=input_ref,
                expected_workspace_root=(
                    str(record.get("workspace_root"))
                    if _is_nonempty_string(record.get("workspace_root"))
                    else None
                ),
                expected_workspace_id=(
                    str(record.get("workspace_id"))
                    if _is_nonempty_string(record.get("workspace_id"))
                    else None
                ),
            )
        if record.get("runtime_attestation") not in (None, "NONE", "UNSET"):
            if entity.kind == "task":
                checked_attestation(
                    record["runtime_attestation"],
                    agent_id=str(record.get("agent_id")),
                    role="WORKER",
                    model=str(record.get("assigned_model")),
                    tier=str(entity.data.get("worker_tier")),
                )
            elif entity.kind == "qa":
                checked_attestation(
                    record["runtime_attestation"],
                    agent_id=str(record.get("agent_id")),
                    role="QA",
                    model=str(record.get("requested_model")),
                )

    def reverify_phase_evidence(phase_id: str) -> None:
        phase = require_entity(phase_id)
        if phase.data.get("lead_approval_evidence") not in (None, "NONE", "UNSET"):
            checked_approval(
                phase.data["lead_approval_evidence"],
                kind="PHASE",
                entity_id=phase.entity_id,
                approver_role="LEAD",
            )
        for field in ("integration_manifest", "integration_journal"):
            if phase.data.get(field) not in (None, "NONE", "UNSET"):
                checked_ref(phase.data[field])
        for task in [item for item in doc.blocks_of("task") if item.phase_id == phase_id]:
            checked_ref(task.data.get("current_evidence"))
            attempts = task.data.get("attempts", []) or []
            if attempts:
                reverify_attempt(attempts[-1], task)
        for test in [item for item in doc.blocks_of("test") if item.phase_id == phase_id]:
            checked_ref(test.data.get("evidence"))
            results = test.data.get("results", []) or []
            if results:
                reverify_attempt(results[-1], test)
        qa = next((item for item in doc.blocks_of("qa") if item.phase_id == phase_id), None)
        if qa and qa.data.get("attempts"):
            qa_attempt = qa.data["attempts"][-1]
            reverify_attempt(qa_attempt, qa)
            verify_phase_aggregate_state(
                phase_id,
                aggregate_state_id=qa_attempt.get("input_state_id"),
                aggregate_input_manifest=qa_attempt.get("input_manifest"),
            )

    def reverify_plan_evidence_graph() -> None:
        if not verify_evidence:
            return
        for revision_field, evidence_field in (
            ("planning_revision", "planning_evidence"),
            ("execution_baseline", "execution_evidence"),
        ):
            reference = checked_ref(doc.metadata.get(evidence_field))
            errors = validate_evidence_manifest_reference(
                reference,
                project_root=root,
                expected_plan_id=str(doc.metadata.get("plan_id")),
                expected_entity_id="PLAN",
                expected_stage="BASELINE",
                expected_attempt=0,
                check_current_state=False,
            )
            if errors:
                raise errors[0]
            binding_errors = validate_revision_binding(
                doc.metadata.get(revision_field),
                evidence_manifest_ref=reference,
                project_root=root,
                check_current_revision=False,
            )
            if binding_errors:
                raise binding_errors[0]

        if doc.metadata.get("last_resolution_evidence") not in (None, "NONE", "UNSET"):
            checked_ref(doc.metadata["last_resolution_evidence"])

        for finding in doc.metadata.get("finding_ledger", []) or []:
            opened_by = finding.get("opened_by")
            if not isinstance(opened_by, dict):
                raise PlanError("FINDING_INVALID", "finding opened_by is invalid")
            opened_reference = checked_ref(opened_by.get("report_manifest"))
            match = re.fullmatch(
                r"(QA-(?:[1-9][0-9]*|FINAL))/A([0-9]{4})/F[0-9]{3}",
                str(finding.get("finding_ref")),
            )
            if match:
                qa = require_entity(match.group(1))
                opened_attempt_number = int(match.group(2))
                opened_attempt = next(
                    (
                        item
                        for item in qa.data.get("attempts", []) or []
                        if int(item.get("attempt", -1)) == opened_attempt_number
                    ),
                    None,
                )
                if (
                    opened_attempt is None
                    or opened_attempt.get("evidence_manifest") != opened_reference
                ):
                    raise PlanError(
                        "FINDING_INVALID",
                        f"{finding.get('finding_ref')} is not bound to its opening QA attempt",
                    )
                reverify_attempt(opened_attempt, qa)
            for address in finding.get("addressed_by", []) or []:
                checked_ref(address.get("report_manifest"))
            resolved_by = finding.get("resolved_by")
            if finding.get("status") == "RESOLVED":
                if not isinstance(resolved_by, dict):
                    raise PlanError("FINDING_INVALID", "Resolved finding has no resolution record")
                checked_ref(resolved_by.get("resolution_evidence"))

    def require_current_source_state(expected_state_id: Any) -> None:
        if not verify_evidence:
            return
        try:
            current_state_id = workspace_state_id(
                collect_workspace(root.resolve(), list(WORKSPACE_DEFAULT_IGNORES))
            )
        except (OSError, WorkspaceGuardError) as exc:
            raise PlanError("EVIDENCE_STATE_MISMATCH", str(exc)) from exc
        if current_state_id != expected_state_id:
            raise PlanError("EVIDENCE_STATE_MISMATCH", "Current source state differs from QA input state")

    def checked_integration(
        manifest_ref: Any,
        journal_ref: Any,
        *,
        expected_state_id: Any,
        expected_phase_id: str,
    ) -> tuple[Any, Any]:
        manifest_reference = checked_ref(manifest_ref)
        journal_reference = checked_ref(journal_ref)
        if not verify_evidence:
            return manifest_reference, journal_reference
        evidence_root = (root / "dev-plan" / "evidence").resolve()
        manifest_path = (root / str(manifest_reference["path"])).resolve()
        journal_path = (root / str(journal_reference["path"])).resolve()
        if not manifest_path.is_relative_to(evidence_root) or not journal_path.is_relative_to(evidence_root):
            raise PlanError("EVIDENCE_PATH_INVALID", "Integration evidence must be under dev-plan/evidence/")
        workspace_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        phase_tasks = [
            item for item in doc.blocks_of("task") if item.phase_id == expected_phase_id
        ]
        contract_allowed = sorted(
            {
                str(pattern)
                for task in phase_tasks
                for pattern in (task.data.get("allowed_paths", []) or [])
            }
        )
        contract_new = sorted(
            {
                str(pattern)
                for task in phase_tasks
                for pattern in (task.data.get("allowed_new_paths", []) or [])
            }
        )
        contract_value = {
            "plan_id": str(doc.metadata.get("plan_id")),
            "phase_id": expected_phase_id,
            "allowed_paths": contract_allowed,
            "allowed_new_paths": contract_new,
        }
        contract_sha256 = hashlib.sha256(
            json.dumps(
                contract_value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        changes = journal.get("changes")
        if not isinstance(changes, dict):
            raise PlanError("EVIDENCE_STATE_MISMATCH", "Integration journal changes are invalid")
        contract_violations = [
            path
            for path in [*changes.get("modified", []), *changes.get("deleted", [])]
            if not any(path_matches_restricted(path, pattern) for pattern in contract_allowed)
        ]
        contract_violations.extend(
            path
            for path in changes.get("added", [])
            if not any(path_matches_restricted(path, pattern) for pattern in contract_new)
        )
        if (journal_path.parent / "COMMITTED.json").exists():
            raise PlanError("EVIDENCE_STATE_MISMATCH", "Integration journal is already committed")
        if (
            workspace_manifest.get("schema") != "codex-workspace-manifest/v1"
            or Path(str(workspace_manifest.get("workspace_root"))).resolve() != root.resolve()
            or workspace_manifest.get("state_id") != expected_state_id
            or workspace_manifest.get("state_id")
            != workspace_state_id(workspace_manifest.get("files", []))
        ):
            raise PlanError("EVIDENCE_STATE_MISMATCH", "Integrated workspace manifest is invalid")
        if (
            journal.get("schema") != "codex-integration-journal/v1"
            or journal.get("status") != "INTEGRATED"
            or Path(str(journal.get("source_root"))).resolve() != root.resolve()
            or journal.get("post_state_id") != expected_state_id
            or Path(str(journal.get("output_manifest"))).resolve() != manifest_path
            or Path(str(journal.get("plan_file"))).resolve() != doc.path.resolve()
            or journal.get("plan_id") != doc.metadata.get("plan_id")
            or journal.get("phase_id") != expected_phase_id
            or journal.get("expected_plan_sha256") != text_sha256(doc.text)
            or journal.get("expected_document_version") != doc.metadata.get("document_version")
            or journal.get("allowed_paths") != contract_allowed
            or journal.get("allowed_new_paths") != contract_new
            or journal.get("path_contract_sha256") != contract_sha256
            or contract_violations
        ):
            raise PlanError("EVIDENCE_STATE_MISMATCH", "Integration journal is invalid")
        require_current_source_state(expected_state_id)
        return manifest_reference, journal_reference

    if name == "PLAN_READY":
        if doc.metadata.get("status") != "DRAFT":
            raise PlanError("EVENT_FROM_MISMATCH", "PLAN_READY requires DRAFT")
        revision = payload.get("planning_revision")
        evidence = payload.get("planning_evidence")
        if revision in (None, "UNSET", "NONE"):
            raise PlanError("EVENT_PAYLOAD_INVALID", "planning_revision is required")
        doc.metadata["planning_revision"] = revision
        doc.metadata["planning_evidence"] = checked_manifest(
            evidence,
            entity_id="PLAN",
            stage="BASELINE",
            attempt=0,
        )
        if verify_evidence:
            revision_errors = validate_revision_binding(
                revision,
                evidence_manifest_ref=doc.metadata["planning_evidence"],
                project_root=root,
                check_current_revision=True,
            )
            if revision_errors:
                raise revision_errors[0]
        doc.metadata["status"] = "READY"
    elif name == "EXECUTION_STARTED":
        if doc.metadata.get("status") != "READY":
            raise PlanError("EVENT_FROM_MISMATCH", "EXECUTION_STARTED requires READY")
        baseline = payload.get("execution_baseline")
        evidence = payload.get("execution_evidence")
        if baseline in (None, "UNSET", "NONE"):
            raise PlanError("EVENT_PAYLOAD_INVALID", "execution_baseline is required")
        doc.metadata["execution_baseline"] = baseline
        doc.metadata["execution_evidence"] = checked_manifest(
            evidence,
            entity_id="PLAN",
            stage="BASELINE",
            attempt=0,
        )
        if verify_evidence:
            revision_errors = validate_revision_binding(
                baseline,
                evidence_manifest_ref=doc.metadata["execution_evidence"],
                project_root=root,
                check_current_revision=True,
            )
            if revision_errors:
                raise revision_errors[0]
        doc.metadata["status"] = "IN_PROGRESS"
        first = sorted(doc.blocks_of("phase"), key=lambda block: block.heading_line)[0]
        first.data["status"] = "IN_PROGRESS"
        doc.metadata["current_phase"] = first.entity_id
    elif name == "TASK_ASSIGNED":
        require_plan_status({"IN_PROGRESS"})
        block = require_entity(str(payload.get("task_id")))
        require_status(block, {"PENDING", "REWORK"})
        require_active_phase(block)
        worker_tier = str(require_value(payload.get("worker_tier"), "worker_tier"))
        assigned_model = str(require_value(payload.get("assigned_model"), "assigned_model"))
        if worker_tier not in {"TERRA", "LUNA"}:
            raise PlanError("EVENT_PAYLOAD_INVALID", "worker_tier must be TERRA or LUNA")
        if block.data.get("complexity") == "COMPLEX" and worker_tier != "LUNA":
            raise PlanError("GUARD_FAILED", "COMPLEX DEV requires an available Luna Worker")
        for dependency_id in block.data.get("dependencies", []) or []:
            dependency = require_entity(dependency_id)
            if dependency.data.get("status") not in {"WORKER_DONE", "DONE"}:
                raise PlanError("GUARD_FAILED", f"Dependency {dependency_id} is not complete", entity=block.entity_id)
            for test_id in dependency.data.get("verification_tests", []) or []:
                if require_entity(test_id).data.get("status") != "PASS":
                    raise PlanError("GUARD_FAILED", f"Dependency TEST {test_id} is not PASS", entity=block.entity_id)
        input_state_id = require_value(payload.get("input_state_id"), "input_state_id")
        candidate_writes = [
            *list(block.data.get("allowed_paths", []) or []),
            *list(block.data.get("allowed_new_paths", []) or []),
        ]
        candidate_reads = list(block.data.get("read_paths", []) or [])
        for other in doc.blocks_of("task"):
            if other.entity_id == block.entity_id or other.data.get("status") not in {
                "ASSIGNED",
                "IN_PROGRESS",
                "WORKER_DONE",
            }:
                continue
            other_writes = [
                *list(other.data.get("allowed_paths", []) or []),
                *list(other.data.get("allowed_new_paths", []) or []),
            ]
            other_reads = list(other.data.get("read_paths", []) or [])
            overlaps = (
                path_sets_overlap(candidate_writes, other_writes)
                or path_sets_overlap(candidate_writes, other_reads)
                or path_sets_overlap(other_writes, candidate_reads)
            )
            if not overlaps:
                continue
            if other.data.get("status") == "WORKER_DONE":
                attempts = other.data.get("attempts", []) or []
                latest = attempts[-1] if attempts else {}
                if (
                    latest.get("validity") == "VALID"
                    and state_reaches(latest.get("output_state_id"), input_state_id)
                ):
                    continue
            if overlaps:
                raise PlanError(
                    "GUARD_FAILED",
                    f"Path ownership conflicts with active task {other.entity_id}; serialize the assignments",
                    entity=block.entity_id,
                )
        lease_expires_at = require_value(payload.get("lease_expires_at"), "lease_expires_at")
        if not _future_iso_datetime(lease_expires_at):
            raise PlanError("EVENT_PAYLOAD_INVALID", "lease_expires_at must be a future ISO-8601 timestamp")
        agent_id = str(require_value(payload.get("agent_id"), "agent_id"))
        if any(item.get("agent_id") == agent_id for item in block.data.get("attempts", []) or []):
            raise PlanError("GUARD_FAILED", "Worker agent_id must be fresh for a new attempt", entity=block.entity_id)
        addresses_findings = payload.get("addresses_findings", [])
        if (
            not isinstance(addresses_findings, list)
            or any(not _is_nonempty_string(item) for item in addresses_findings)
            or len(addresses_findings) != len(set(addresses_findings))
        ):
            raise PlanError("EVENT_PAYLOAD_INVALID", "addresses_findings must be a unique string list")
        ledger = doc.metadata.get("finding_ledger", []) or []
        for finding_ref in addresses_findings:
            finding = next(
                (item for item in ledger if item.get("finding_ref") == finding_ref),
                None,
            )
            if not finding or finding.get("status") != "OPEN":
                raise PlanError(
                    "GUARD_FAILED",
                    f"addresses_findings requires an OPEN finding: {finding_ref}",
                    entity=block.entity_id,
                )
            related = set(finding.get("related_entities", []) or [])
            if block.entity_id not in related and block.phase_id not in related:
                raise PlanError(
                    "GUARD_FAILED",
                    f"{finding_ref} is unrelated to {block.entity_id}",
                    entity=block.entity_id,
                )
        workspace_root = str(require_value(payload.get("workspace_root"), "workspace_root"))
        workspace_id = str(require_value(payload.get("workspace_id"), "workspace_id"))
        require_disposable_workspace(workspace_root, workspace_id)
        runtime_attestation, attestation = checked_attestation(
            payload.get("runtime_attestation"),
            agent_id=agent_id,
            role="WORKER",
            model=assigned_model,
            tier=worker_tier,
        )
        if attestation and (
            attestation.get("workspace_root") != workspace_root
            or attestation.get("workspace_id") != workspace_id
        ):
            raise PlanError("RUNTIME_ATTESTATION_INVALID", "Workspace identity differs from runtime attestation")
        next_attempt = int(block.data.get("attempt", 0)) + 1
        contract_manifest = checked_manifest(
            payload.get("contract_manifest"),
            entity_id=block.entity_id,
            stage="INPUT",
            attempt=next_attempt,
            expected_input_state_id=input_state_id,
            expected_workspace_root=workspace_root,
            expected_workspace_id=workspace_id,
        )
        block.data["attempt"] = next_attempt
        block.data["worker_tier"] = worker_tier
        block.data["assigned_model"] = assigned_model
        block.data["current_run"] = {
            "attempt": block.data["attempt"],
            "agent_id": agent_id,
            "requested_model": assigned_model,
            "context_mode": "NONE",
            "input_state_id": input_state_id,
            "workspace_root": workspace_root,
            "workspace_id": workspace_id,
            "runtime_attestation": runtime_attestation,
            "contract_manifest": contract_manifest,
            "addresses_findings": list(addresses_findings),
            "started_at": "NONE",
            "lease_expires_at": lease_expires_at,
        }
        block.data["status"] = "ASSIGNED"
    elif name == "TASK_STARTED":
        require_plan_status({"IN_PROGRESS"})
        block = require_entity(str(payload.get("task_id")))
        require_status(block, {"ASSIGNED"})
        require_active_phase(block)
        run = block.data.get("current_run")
        if not isinstance(run, dict):
            raise PlanError("GUARD_FAILED", "Task current_run is missing", entity=block.entity_id)
        identity = {
            "attempt": run.get("attempt"),
            "agent_id": run.get("agent_id"),
            "input_state_id": run.get("input_state_id"),
            "lease_expires_at": run.get("lease_expires_at"),
        }
        for field, expected in identity.items():
            if payload.get(field) != expected:
                raise PlanError(
                    "GUARD_FAILED",
                    f"TASK_STARTED {field} does not match the current assignment",
                    entity=block.entity_id,
                )
        if not _future_iso_datetime(run.get("lease_expires_at")):
            raise PlanError("GUARD_FAILED", "Worker assignment lease has expired", entity=block.entity_id)
        block.data["status"] = "IN_PROGRESS"
        run["started_at"] = payload.get("started_at", now_iso())
    elif name == "TEST_STARTED":
        require_plan_status({"IN_PROGRESS"})
        block = require_entity(str(payload.get("test_id")))
        require_status(block, {"PENDING", "FAIL"})
        require_active_phase(block)
        task_refs = list(payload.get("task_refs", []))
        if set(task_refs) != set(block.data.get("for_tasks", []) or []):
            raise PlanError("EVENT_PAYLOAD_INVALID", "task_refs must match TEST for_tasks", entity=block.entity_id)
        for task_id in task_refs:
            task = require_entity(task_id)
            if task.data.get("status") not in {"IN_PROGRESS", "WORKER_DONE"}:
                raise PlanError("GUARD_FAILED", f"{task_id} is not ready for TEST", entity=block.entity_id)
        tested_state_id = require_value(payload.get("tested_state_id"), "tested_state_id")
        event_command_sha = require_value(payload.get("command_sha256"), "command_sha256")
        if block.data.get("kind") == "command" and event_command_sha != block.data.get("command_sha256"):
            raise PlanError("GUARD_FAILED", "TEST command_sha256 differs from the plan", entity=block.entity_id)
        require_value(payload.get("deadline"), "deadline")
        next_attempt = int(block.data.get("attempt", 0)) + 1
        input_manifest = checked_manifest(
            payload.get("input_manifest"),
            entity_id=block.entity_id,
            stage="INPUT",
            attempt=next_attempt,
            expected_input_state_id=tested_state_id,
        )
        block.data["attempt"] = next_attempt
        block.data["current_run"] = {
            "attempt": block.data["attempt"],
            "task_refs": task_refs,
            "tested_state_id": tested_state_id,
            "command_sha256": event_command_sha,
            "input_manifest": input_manifest,
            "started_at": payload.get("started_at", now_iso()),
            "deadline": payload.get("deadline"),
        }
        block.data["status"] = "RUNNING"
    elif name == "TEST_REPORTED":
        require_plan_status({"IN_PROGRESS"})
        block = require_entity(str(payload.get("test_id")))
        require_status(block, {"RUNNING"})
        require_active_phase(block)
        result = str(payload.get("result"))
        if result not in {"PASS", "FAIL", "BLOCKED"}:
            raise PlanError("EVENT_PAYLOAD_INVALID", "TEST_REPORTED result is invalid")
        run = block.data.get("current_run")
        if not isinstance(run, dict):
            raise PlanError("GUARD_FAILED", "Test current_run is missing", entity=block.entity_id)
        record = {
            "attempt": run.get("attempt"),
            "validity": "VALID",
            "task_refs": run.get("task_refs", []),
            "tested_state_id": run.get("tested_state_id"),
            "command_sha256": run.get("command_sha256"),
            "input_manifest": run.get("input_manifest"),
            "result": result,
            "evidence_manifest": checked_manifest(
                payload.get("evidence_manifest"),
                entity_id=block.entity_id,
                stage="RESULT",
                attempt=int(run.get("attempt")),
                expected_input_state_id=run.get("tested_state_id"),
                expected_output_state_id=run.get("tested_state_id"),
                expected_input_manifest=run.get("input_manifest"),
            ),
        }
        block.data.setdefault("results", []).append(record)
        block.data["status"] = result
        block.data["actual"] = payload.get("actual", result)
        block.data["evidence"] = record["evidence_manifest"]
        block.data["current_run"] = "NONE"
        if result == "BLOCKED":
            _cascade_block(doc, block, str(payload.get("reason", "TEST blocked")), list(payload.get("unblock_conditions", [])))
    elif name == "WORKER_REPORTED":
        require_plan_status({"IN_PROGRESS"})
        block = require_entity(str(payload.get("task_id")))
        require_status(block, {"IN_PROGRESS"})
        require_active_phase(block)
        output_state = require_value(payload.get("output_state_id"), "output_state_id")
        for test_id in block.data.get("verification_tests", []) or []:
            test = require_entity(test_id)
            if test.data.get("status") != "PASS":
                raise PlanError("GUARD_FAILED", f"Required test {test_id} is not PASS", entity=block.entity_id)
            results = test.data.get("results", []) or []
            if not results or results[-1].get("tested_state_id") != output_state:
                raise PlanError("GUARD_FAILED", f"Required test {test_id} did not test the Worker output state", entity=block.entity_id)
        run = block.data.get("current_run")
        if not isinstance(run, dict):
            raise PlanError("GUARD_FAILED", "Task current_run is missing", entity=block.entity_id)
        if not _future_iso_datetime(run.get("lease_expires_at")):
            raise PlanError(
                "GUARD_FAILED",
                "Worker assignment lease expired before WORKER_REPORTED",
                entity=block.entity_id,
            )
        record = {
            "attempt": run.get("attempt"),
            "validity": "VALID",
            "assigned_model": block.data.get("assigned_model"),
            "actual_model": payload.get("actual_model", "NOT_REPORTED"),
            "agent_id": run.get("agent_id"),
            "context_mode": run.get("context_mode"),
            "input_state_id": run.get("input_state_id"),
            "output_state_id": output_state,
            "workspace_root": run.get("workspace_root"),
            "workspace_id": run.get("workspace_id"),
            "runtime_attestation": run.get("runtime_attestation"),
            "contract_manifest": run.get("contract_manifest"),
            "addresses_findings": list(run.get("addresses_findings", [])),
            "evidence_manifest": checked_manifest(
                payload.get("evidence_manifest"),
                entity_id=block.entity_id,
                stage="RESULT",
                attempt=int(run.get("attempt")),
                expected_input_state_id=run.get("input_state_id"),
                expected_output_state_id=output_state,
                expected_input_manifest=run.get("contract_manifest"),
                expected_workspace_root=str(run.get("workspace_root")),
                expected_workspace_id=str(run.get("workspace_id")),
            ),
        }
        if record["actual_model"] not in {block.data.get("assigned_model"), "NOT_REPORTED"}:
            raise PlanError("GUARD_FAILED", "Worker actual_model conflicts with assigned_model", entity=block.entity_id)
        block.data.setdefault("attempts", []).append(record)
        for finding_ref in record["addresses_findings"]:
            finding = next(
                (
                    item
                    for item in doc.metadata.get("finding_ledger", []) or []
                    if item.get("finding_ref") == finding_ref
                ),
                None,
            )
            if not finding or finding.get("status") != "OPEN":
                raise PlanError("GUARD_FAILED", f"Addressed finding is no longer OPEN: {finding_ref}")
            finding.setdefault("addressed_by", []).append(
                {
                    "task_id": block.entity_id,
                    "attempt": record["attempt"],
                    "report_manifest": record["evidence_manifest"],
                }
            )
        block.data["current_evidence"] = record["evidence_manifest"]
        block.data["status"] = "WORKER_DONE"
        block.data["current_run"] = "NONE"
    elif name == "WORKER_ATTEMPT_INVALIDATED":
        require_plan_status({"IN_PROGRESS", "BLOCKED"})
        block = require_entity(str(payload.get("task_id")))
        require_status(block, {"ASSIGNED", "IN_PROGRESS"})
        run = block.data.get("current_run")
        if not isinstance(run, dict):
            raise PlanError("GUARD_FAILED", "Task current_run is missing", entity=block.entity_id)
        for field in ("attempt", "agent_id", "input_state_id"):
            if payload.get(field) != run.get(field):
                raise PlanError(
                    "GUARD_FAILED",
                    f"WORKER_ATTEMPT_INVALIDATED {field} does not match current_run",
                    entity=block.entity_id,
                )
        block.data.setdefault("attempts", []).append(
            {
                "attempt": run.get("attempt"),
                "validity": "INVALID",
                "assigned_model": block.data.get("assigned_model"),
                "input_state_id": run.get("input_state_id"),
                "output_state_id": "NONE",
                "reason": payload.get("reason", "attempt invalidated"),
                "evidence_manifest": payload.get("evidence_manifest", "NONE"),
            }
        )
        block.data["current_run"] = "NONE"
        block.data["status"] = "REWORK"
        block.data["worker_tier"] = "UNASSIGNED"
        block.data["assigned_model"] = "UNASSIGNED"
        if payload.get("block"):
            _cascade_block(
                doc,
                block,
                str(require_value(payload.get("reason"), "reason")),
                list(payload.get("unblock_conditions", [])),
            )
    elif name in {"PHASE_QA_STARTED", "PLAN_QA_STARTED"}:
        require_plan_status({"IN_PROGRESS", "QA"})
        qa_id = str(payload.get("qa_id", "QA-FINAL" if name == "PLAN_QA_STARTED" else ""))
        qa = require_entity(qa_id)
        if qa.kind != "qa":
            raise PlanError("EVENT_PAYLOAD_INVALID", f"{qa.entity_id} is not a QA entity")
        require_status(qa, {"PENDING"})
        if name == "PHASE_QA_STARTED":
            if qa.entity_id == "QA-FINAL" or qa.phase_id is None:
                raise PlanError("EVENT_PAYLOAD_INVALID", "PHASE_QA_STARTED requires a Phase QA entity")
            phase = require_entity(str(payload.get("phase_id") or qa.phase_id))
            if phase.kind != "phase" or qa.phase_id != phase.entity_id:
                raise PlanError("EVENT_PAYLOAD_INVALID", "Phase QA must belong to the requested Phase")
            require_status(phase, {"IN_PROGRESS", "QA"})
            if phase.entity_id != doc.metadata.get("current_phase"):
                raise PlanError("GUARD_FAILED", f"{phase.entity_id} is not the current Phase")
            for task in [block for block in doc.blocks_of("task") if block.phase_id == phase.entity_id]:
                if task.data.get("status") not in {"WORKER_DONE", "DONE"}:
                    raise PlanError("GUARD_FAILED", f"{task.entity_id} is not ready for Phase QA")
            for test in [block for block in doc.blocks_of("test") if block.phase_id == phase.entity_id]:
                if test.data.get("status") != "PASS":
                    raise PlanError("GUARD_FAILED", f"{test.entity_id} is not PASS")
            phase.data["status"] = "QA"
        else:
            if qa.entity_id != "QA-FINAL" or qa.phase_id is not None:
                raise PlanError("EVENT_PAYLOAD_INVALID", "PLAN_QA_STARTED requires QA-FINAL")
            if doc.metadata.get("status") not in {"IN_PROGRESS", "QA"}:
                raise PlanError("EVENT_FROM_MISMATCH", "PLAN_QA_STARTED requires IN_PROGRESS or QA")
            if any(phase.data.get("status") != "DONE" for phase in doc.blocks_of("phase")):
                raise PlanError("GUARD_FAILED", "All Phases must be DONE before final QA")
            doc.metadata["status"] = "QA"
            doc.metadata["current_phase"] = "NONE"
        requested_model = str(require_value(payload.get("requested_model"), "requested_model"))
        if requested_model != doc.metadata.get("qa_model"):
            raise PlanError("GUARD_FAILED", "QA requested_model must equal plan qa_model", entity=qa.entity_id)
        actual_model = str(payload.get("actual_model", "NOT_REPORTED"))
        if actual_model not in {doc.metadata.get("qa_model"), "NOT_REPORTED"}:
            raise PlanError("GUARD_FAILED", "QA actual_model must equal plan qa_model", entity=qa.entity_id)
        if payload.get("context_mode") != "NONE":
            raise PlanError("GUARD_FAILED", "Independent QA requires context_mode NONE", entity=qa.entity_id)
        input_state_id = require_value(payload.get("input_state_id"), "input_state_id")
        require_value(payload.get("deadline"), "deadline")
        agent_id = str(require_value(payload.get("agent_id"), "agent_id"))
        prior_qa_agents = {
            attempt.get("agent_id")
            for item in doc.blocks_of("qa")
            for attempt in item.data.get("attempts", []) or []
        }
        if agent_id in prior_qa_agents:
            raise PlanError("GUARD_FAILED", "Independent QA requires a fresh agent_id", entity=qa.entity_id)
        workspace_root = str(require_value(payload.get("workspace_root"), "workspace_root"))
        workspace_id = str(require_value(payload.get("workspace_id"), "workspace_id"))
        require_disposable_workspace(workspace_root, workspace_id)
        runtime_attestation, attestation = checked_attestation(
            payload.get("runtime_attestation"),
            agent_id=agent_id,
            role="QA",
            model=requested_model,
        )
        if attestation and (
            attestation.get("workspace_root") != workspace_root
            or attestation.get("workspace_id") != workspace_id
        ):
            raise PlanError("RUNTIME_ATTESTATION_INVALID", "QA workspace differs from runtime attestation")
        next_attempt = int(qa.data.get("current_attempt", 0)) + 1
        qa_input_manifest = checked_manifest(
            payload.get("input_manifest"),
            entity_id=qa.entity_id,
            stage="INPUT",
            attempt=next_attempt,
            expected_input_state_id=input_state_id,
            expected_workspace_root=workspace_root,
            expected_workspace_id=workspace_id,
        )
        if name == "PHASE_QA_STARTED":
            verify_phase_aggregate_state(
                str(payload.get("phase_id") or qa.phase_id),
                aggregate_state_id=input_state_id,
                aggregate_input_manifest=qa_input_manifest,
            )
        qa.data["current_attempt"] = next_attempt
        qa.data["current_run"] = {
            "attempt": qa.data["current_attempt"],
            "agent_id": agent_id,
            "requested_model": requested_model,
            "actual_model": actual_model,
            "context_mode": "NONE",
            "input_state_id": input_state_id,
            "workspace_root": workspace_root,
            "workspace_id": workspace_id,
            "runtime_attestation": runtime_attestation,
            "contract_manifest": qa_input_manifest,
            "started_at": payload.get("started_at", now_iso()),
            "deadline": payload.get("deadline"),
        }
        qa.data["status"] = "RUNNING"
        qa.data["verdict"] = "PENDING"
    elif name in {"PHASE_QA_REPORTED", "FINAL_QA_REPORTED"}:
        require_plan_status({"IN_PROGRESS", "QA", "BLOCKED"})
        qa_id = str(payload.get("qa_id", "QA-FINAL" if name == "FINAL_QA_REPORTED" else ""))
        qa = require_entity(qa_id)
        if qa.kind != "qa":
            raise PlanError("EVENT_PAYLOAD_INVALID", f"{qa.entity_id} is not a QA entity")
        if name == "PHASE_QA_REPORTED":
            if qa.entity_id == "QA-FINAL" or qa.phase_id is None:
                raise PlanError("EVENT_PAYLOAD_INVALID", "PHASE_QA_REPORTED requires a Phase QA entity")
            phase_id = payload.get("phase_id", qa.phase_id)
            if phase_id != qa.phase_id:
                raise PlanError("EVENT_PAYLOAD_INVALID", "Phase QA report is bound to its owning Phase")
        elif qa.entity_id != "QA-FINAL" or qa.phase_id is not None:
            raise PlanError("EVENT_PAYLOAD_INVALID", "FINAL_QA_REPORTED requires QA-FINAL")
        require_status(qa, {"RUNNING"})
        verdict = str(payload.get("verdict"))
        if verdict not in {"PASS", "FAIL", "BLOCKED"}:
            raise PlanError("EVENT_PAYLOAD_INVALID", "QA verdict is invalid")
        run = qa.data.get("current_run")
        if not isinstance(run, dict):
            raise PlanError("GUARD_FAILED", "QA current_run is missing", entity=qa.entity_id)
        if run.get("actual_model") not in {doc.metadata.get("qa_model"), "NOT_REPORTED"} or run.get("context_mode") != "NONE":
            raise PlanError("GUARD_FAILED", "QA independence/model attestation is invalid", entity=qa.entity_id)
        resolved_findings = payload.get("resolved_findings", [])
        if (
            not isinstance(resolved_findings, list)
            or any(not _is_nonempty_string(item) for item in resolved_findings)
            or len(resolved_findings) != len(set(resolved_findings))
        ):
            raise PlanError("EVENT_PAYLOAD_INVALID", "resolved_findings must be a unique string list")
        for finding_ref in resolved_findings:
            finding = next(
                (
                    item
                    for item in doc.metadata.get("finding_ledger", []) or []
                    if item.get("finding_ref") == finding_ref
                ),
                None,
            )
            if (
                not finding
                or finding.get("status") != "OPEN"
                or not finding.get("addressed_by")
            ):
                raise PlanError(
                    "GUARD_FAILED",
                    f"resolved_findings requires an addressed OPEN finding: {finding_ref}",
                )
        record = {
            "attempt": run.get("attempt"),
            "validity": "VALID",
            "verdict": verdict,
            "agent_id": run.get("agent_id"),
            "requested_model": run.get("requested_model"),
            "actual_model": run.get("actual_model", "NOT_REPORTED"),
            "context_mode": run.get("context_mode"),
            "input_state_id": run.get("input_state_id"),
            "workspace_root": run.get("workspace_root"),
            "workspace_id": run.get("workspace_id"),
            "runtime_attestation": run.get("runtime_attestation"),
            "input_manifest": run.get("contract_manifest"),
            "resolved_findings": list(resolved_findings),
            "evidence_manifest": checked_manifest(
                payload.get("evidence_manifest"),
                entity_id=qa.entity_id,
                stage="RESULT",
                attempt=int(run.get("attempt")),
                expected_input_state_id=run.get("input_state_id"),
                expected_output_state_id=run.get("input_state_id"),
                expected_input_manifest=run.get("contract_manifest"),
                expected_workspace_root=str(run.get("workspace_root")),
                expected_workspace_id=str(run.get("workspace_id")),
            ),
        }
        qa.data.setdefault("attempts", []).append(record)
        qa.data["current_run"] = "NONE"
        qa.data["status"] = "FINISHED"
        qa.data["verdict"] = verdict
        _append_findings(doc, qa, record, payload.get("findings", []))
        if verdict == "BLOCKED":
            _cascade_block(doc, qa, payload.get("reason", "QA verdict BLOCKED"))
    elif name == "QA_ATTEMPT_INVALIDATED":
        require_plan_status({"IN_PROGRESS", "QA", "BLOCKED"})
        qa = require_entity(str(payload.get("qa_id")))
        require_status(qa, {"RUNNING"})
        run = qa.data.get("current_run")
        if not isinstance(run, dict):
            raise PlanError("GUARD_FAILED", "QA current_run is missing", entity=qa.entity_id)
        for field in ("attempt", "agent_id", "input_state_id"):
            if payload.get(field) != run.get(field):
                raise PlanError(
                    "GUARD_FAILED",
                    f"QA_ATTEMPT_INVALIDATED {field} does not match current_run",
                    entity=qa.entity_id,
                )
        qa.data.setdefault("attempts", []).append(
            {
                "attempt": run.get("attempt"),
                "validity": "INVALID",
                "verdict": "PENDING",
                "agent_id": run.get("agent_id"),
                "requested_model": run.get("requested_model"),
                "actual_model": run.get("actual_model", "NOT_REPORTED"),
                "context_mode": run.get("context_mode"),
                "input_state_id": run.get("input_state_id"),
                "reason": payload.get("reason", "QA attempt invalidated"),
                "evidence_manifest": payload.get("evidence_manifest", "NONE"),
            }
        )
        qa.data["current_run"] = "NONE"
        qa.data["status"] = "PENDING"
        qa.data["verdict"] = "PENDING"
        if payload.get("block"):
            _cascade_block(doc, qa, payload.get("reason", "QA integrity uncertain"))
    elif name == "PHASE_APPROVED":
        require_plan_status({"IN_PROGRESS"})
        phase = require_entity(str(payload.get("phase_id")))
        require_status(phase, {"QA"})
        qa = next((block for block in doc.blocks_of("qa") if block.phase_id == phase.entity_id), None)
        if not qa or qa.data.get("status") != "FINISHED" or qa.data.get("verdict") != "PASS":
            raise PlanError("GUARD_FAILED", "Phase QA must PASS before approval", entity=phase.entity_id)
        qa_attempt = _require_current_valid_pass(qa, require_value(payload.get("input_state_id"), "input_state_id"))
        reverify_attempt(qa_attempt, qa)
        reverify_phase_evidence(phase.entity_id)
        verify_phase_aggregate_state(
            phase.entity_id,
            aggregate_state_id=qa_attempt.get("input_state_id"),
            aggregate_input_manifest=qa_attempt.get("input_manifest"),
        )
        integration_manifest, integration_journal = checked_integration(
            payload.get("integration_manifest"),
            payload.get("integration_journal"),
            expected_state_id=payload.get("input_state_id"),
            expected_phase_id=phase.entity_id,
        )
        approval_evidence = checked_approval(
            payload.get("approval_evidence"),
            kind="PHASE",
            entity_id=phase.entity_id,
            approver_role="LEAD",
        )
        for task in [block for block in doc.blocks_of("task") if block.phase_id == phase.entity_id]:
            if task.data.get("status") == "WORKER_DONE":
                task.data["status"] = "DONE"
        phase.data["status"] = "DONE"
        phase.data["lead_approval"] = "APPROVED"
        phase.data["lead_approval_evidence"] = approval_evidence
        phase.data["integration_manifest"] = integration_manifest
        phase.data["integration_journal"] = integration_journal
        phase_blocks = sorted(doc.blocks_of("phase"), key=lambda block: block.heading_line)
        current_index = phase_blocks.index(phase)
        next_phase = next(
            (item for item in phase_blocks[current_index + 1 :] if item.data.get("status") in {"PENDING", "REWORK_PENDING"}),
            None,
        )
        if next_phase:
            next_phase.data["status"] = "IN_PROGRESS"
            doc.metadata["current_phase"] = next_phase.entity_id
        else:
            doc.metadata["status"] = "QA"
            doc.metadata["current_phase"] = "NONE"
    elif name == "REWORK_REQUESTED":
        _apply_rework(doc, payload)
    elif name == "ENTITY_BLOCKED":
        if doc.metadata.get("status") == "COMPLETED":
            raise PlanError("EVENT_FROM_MISMATCH", "A COMPLETED Plan cannot be blocked")
        entity_id = str(payload.get("entity_id", "PLAN"))
        target: EntityBlock | None = None if entity_id == "PLAN" else require_entity(entity_id)
        if target is not None:
            blockable = {
                "phase": {"PENDING", "IN_PROGRESS", "QA", "REWORK_PENDING"},
                "task": {"PENDING", "ASSIGNED", "IN_PROGRESS", "WORKER_DONE", "REWORK"},
                "test": {"PENDING", "RUNNING", "FAIL"},
                "qa": {"PENDING", "RUNNING"},
            }
            if target.data.get("status") not in blockable.get(target.kind, set()):
                raise PlanError(
                    "EVENT_FROM_MISMATCH",
                    f"{target.entity_id} is not in a blockable state",
                    entity=target.entity_id,
                )
        conditions = list(payload.get("unblock_conditions", []))
        if not conditions:
            raise PlanError("EVENT_PAYLOAD_INVALID", "unblock_conditions is required")
        _cascade_block(
            doc,
            target,
            str(require_value(payload.get("reason"), "reason")),
            conditions,
        )
    elif name == "BLOCK_CLEARED":
        if doc.metadata.get("status") != "BLOCKED":
            raise PlanError("EVENT_FROM_MISMATCH", "BLOCK_CLEARED requires a BLOCKED Plan")
        doc.metadata["last_resolution_evidence"] = checked_ref(payload.get("resolution_evidence"))
        _clear_block(doc, payload)
    elif name == "FINDING_RESOLVED":
        finding_ref = require_value(payload.get("finding_ref"), "finding_ref")
        finding = next(
            (
                item
                for item in doc.metadata.get("finding_ledger", []) or []
                if item.get("finding_ref") == finding_ref
            ),
            None,
        )
        if not finding or finding.get("status") != "OPEN":
            raise PlanError("GUARD_FAILED", "FINDING_RESOLVED requires an OPEN finding")
        qa = require_entity(str(require_value(payload.get("qa_id"), "qa_id")))
        if qa.data.get("status") != "FINISHED" or qa.data.get("verdict") != "PASS":
            raise PlanError("GUARD_FAILED", "FINDING_RESOLVED requires a PASS QA")
        qa_attempt = _require_current_valid_pass(qa, require_value(payload.get("input_state_id"), "input_state_id"))
        reverify_attempt(qa_attempt, qa)
        if finding_ref not in set(qa_attempt.get("resolved_findings", []) or []):
            raise PlanError("GUARD_FAILED", "PASS QA report did not declare this resolved finding")
        addressed_by = finding.get("addressed_by", []) or []
        if not addressed_by:
            raise PlanError("GUARD_FAILED", "Finding has no successful addressing Worker attempt")
        valid_address_found = False
        for address in addressed_by:
            task = require_entity(str(address.get("task_id")))
            attempt = next(
                (
                    item
                    for item in task.data.get("attempts", []) or []
                    if item.get("attempt") == address.get("attempt")
                ),
                None,
            )
            if (
                attempt
                and attempt.get("validity") == "VALID"
                and finding_ref in (attempt.get("addresses_findings", []) or [])
                and attempt.get("evidence_manifest") == address.get("report_manifest")
            ):
                reverify_attempt(attempt, task)
                valid_address_found = True
                break
        if not valid_address_found:
            raise PlanError("GUARD_FAILED", "No current VALID Worker attempt addresses this finding")
        resolution_evidence = checked_ref(payload.get("resolution_evidence"))
        finding["status"] = "RESOLVED"
        finding["resolved_by"] = {
            "qa_id": qa.entity_id,
            "qa_attempt": qa.data.get("current_attempt"),
            "resolution_evidence": resolution_evidence,
        }
    elif name == "RISK_ACCEPTED":
        _accept_risk(
            doc,
            payload,
            lambda value: checked_approval(
                value,
                kind="RISK",
                entity_id=str(payload.get("risk_id")),
                approver_role="USER",
            ),
        )
    elif name == "PLAN_APPROVED":
        if doc.metadata.get("status") != "QA":
            raise PlanError("EVENT_FROM_MISMATCH", "PLAN_APPROVED requires QA")
        final = require_entity("QA-FINAL")
        if final.data.get("status") != "FINISHED" or final.data.get("verdict") != "PASS":
            raise PlanError("GUARD_FAILED", "QA-FINAL must PASS")
        final_attempt = _require_current_valid_pass(final, require_value(payload.get("input_state_id"), "input_state_id"))
        reverify_attempt(final_attempt, final)
        reverify_plan_evidence_graph()
        for phase in doc.blocks_of("phase"):
            reverify_phase_evidence(phase.entity_id)
        for risk in doc.metadata.get("residual_risks", []) or []:
            checked_approval(
                risk.get("approval_evidence"),
                kind="RISK",
                entity_id=str(risk.get("risk_id")),
                approver_role="USER",
            )
        require_current_source_state(payload.get("input_state_id"))
        open_findings = [
            item for item in doc.metadata.get("finding_ledger", []) or []
            if item.get("status") == "OPEN"
        ]
        if open_findings:
            raise PlanError("GUARD_FAILED", "Open findings remain")
        existing_risks = doc.metadata.get("residual_risks", [])
        residual_risks = payload.get("residual_risks", existing_risks)
        if not isinstance(residual_risks, list):
            raise PlanError("EVENT_PAYLOAD_INVALID", "residual_risks must be a list")
        if residual_risks != existing_risks:
            raise PlanError(
                "GUARD_FAILED",
                "PLAN_APPROVED may not add, remove, or rewrite previously reviewed residual risks",
            )
        doc.metadata["residual_risks"] = copy.deepcopy(existing_risks)
        doc.metadata["final_approval_evidence"] = checked_approval(
            payload.get("approval_evidence"),
            kind="PLAN",
            entity_id=str(doc.metadata.get("plan_id")),
            approver_role="LEAD",
        )
        doc.metadata["final_approval"] = "APPROVED"
        doc.metadata["status"] = "COMPLETED"
        doc.metadata["current_phase"] = "NONE"
    else:
        raise PlanError("EVENT_UNKNOWN", f"Unsupported event: {name}")

    if not candidate:
        doc.metadata["document_version"] = int(doc.metadata.get("document_version", 0)) + 1
        doc.metadata["updated_at"] = now_iso()


def _append_findings(doc: PlanDocument, qa: EntityBlock, record: dict[str, Any], findings: Any) -> None:
    if not isinstance(findings, list):
        raise PlanError("EVENT_PAYLOAD_INVALID", "findings must be a list")
    ledger = doc.metadata.setdefault("finding_ledger", [])
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            raise PlanError("EVENT_PAYLOAD_INVALID", "finding must be a mapping")
        severity = finding.get("severity")
        if severity not in {"critical", "major", "minor", "info"}:
            raise PlanError("EVENT_PAYLOAD_INVALID", "finding severity must be critical, major, minor, or info")
        status = finding.get("status", "OPEN")
        if status != "OPEN":
            raise PlanError("EVENT_PAYLOAD_INVALID", "new finding status must be OPEN")
        ref = finding.get("finding_ref") or f"{qa.entity_id}/A{int(record['attempt']):04d}/F{index:03d}"
        if any(item.get("finding_ref") == ref for item in ledger):
            raise PlanError("FINDING_DUPLICATE", f"Duplicate finding_ref: {ref}")
        ledger.append(
            {
                "finding_ref": ref,
                "severity": severity,
                "status": status,
                "opened_by": {"report_manifest": record.get("evidence_manifest")},
                "summary": finding.get("summary", "NONE"),
                "related_entities": list(finding.get("related_entities", [])),
                "addressed_by": [],
                "resolved_by": "NONE",
            }
        )


def _require_current_valid_pass(qa: EntityBlock, input_state_id: Any) -> dict[str, Any]:
    attempts = qa.data.get("attempts", []) or []
    current = int(qa.data.get("current_attempt", 0))
    match = next((item for item in reversed(attempts) if int(item.get("attempt", -1)) == current), None)
    if not match or match.get("validity") != "VALID" or match.get("verdict") != "PASS":
        raise PlanError("GUARD_FAILED", f"{qa.entity_id} current attempt is not VALID/PASS")
    if input_state_id is not None and match.get("input_state_id") != input_state_id:
        raise PlanError("GUARD_FAILED", f"{qa.entity_id} input state does not match")
    return match


def _apply_rework(doc: PlanDocument, payload: dict[str, Any]) -> None:
    qa = doc.entity(str(payload.get("qa_id")))
    if qa.data.get("status") != "FINISHED" or qa.data.get("verdict") != "FAIL":
        raise PlanError("GUARD_FAILED", "REWORK_REQUESTED requires FINISHED/FAIL QA")
    affected_phase_ids = list(payload.get("affected_phase_ids", []))
    affected_task_ids = set(payload.get("affected_task_ids", []))
    if not affected_phase_ids:
        if qa.phase_id:
            affected_phase_ids = [qa.phase_id]
        else:
            raise PlanError("EVENT_PAYLOAD_INVALID", "Final QA rework requires affected_phase_ids")
    phases = sorted(doc.blocks_of("phase"), key=lambda block: block.heading_line)
    indices = [index for index, phase in enumerate(phases) if phase.entity_id in affected_phase_ids]
    if not indices or len(indices) != len(set(affected_phase_ids)):
        raise PlanError("EVENT_PAYLOAD_INVALID", "affected_phase_ids are invalid")
    all_tasks = {task.entity_id: task for task in doc.blocks_of("task")}
    if any(task_id not in all_tasks for task_id in affected_task_ids):
        raise PlanError("EVENT_PAYLOAD_INVALID", "affected_task_ids are invalid")
    if any(all_tasks[task_id].phase_id not in set(affected_phase_ids) for task_id in affected_task_ids):
        raise PlanError("EVENT_PAYLOAD_INVALID", "affected DEV must belong to an affected Phase")
    earliest = min(indices)
    for index, phase in enumerate(phases):
        if index < earliest:
            continue
        phase.data["status"] = "IN_PROGRESS" if index == earliest else "REWORK_PENDING"
        phase.data["lead_approval"] = "PENDING"
        phase.data["lead_approval_evidence"] = "NONE"
        phase.data["integration_manifest"] = "NONE"
        phase.data["integration_journal"] = "NONE"
        for task in [block for block in doc.blocks_of("task") if block.phase_id == phase.entity_id]:
            if task.entity_id in affected_task_ids:
                task.data["status"] = "REWORK"
                task.data["rework_count"] = int(task.data.get("rework_count", 0)) + 1
                if task.data["rework_count"] > int(doc.metadata.get("max_rework", 2)):
                    raise PlanError("REWORK_LIMIT", f"{task.entity_id} exceeded max_rework")
            for attempt in task.data.get("attempts", []) or []:
                if attempt.get("validity") == "VALID" and task.entity_id in affected_task_ids:
                    attempt["validity"] = "STALE"
        for test in [block for block in doc.blocks_of("test") if block.phase_id == phase.entity_id]:
            for result in test.data.get("results", []) or []:
                if result.get("validity") == "VALID":
                    result["validity"] = "STALE"
            test.data["status"] = "PENDING"
            test.data["actual"] = "NOT_RUN"
            test.data["evidence"] = "NONE"
            test.data["current_run"] = "NONE"
        phase_qa = next((block for block in doc.blocks_of("qa") if block.phase_id == phase.entity_id), None)
        if phase_qa:
            for attempt in phase_qa.data.get("attempts", []) or []:
                if attempt.get("validity") == "VALID" and attempt.get("verdict") == "PASS":
                    attempt["validity"] = "STALE"
            phase_qa.data["status"] = "PENDING"
            phase_qa.data["verdict"] = "PENDING"
            phase_qa.data["current_run"] = "NONE"
    doc.metadata["status"] = "IN_PROGRESS"
    doc.metadata["current_phase"] = phases[earliest].entity_id
    doc.metadata["final_approval"] = "PENDING"
    doc.metadata["final_approval_evidence"] = "NONE"
    final = doc.entity("QA-FINAL")
    if qa.entity_id == "QA-FINAL":
        final.data["status"] = "PENDING"
        final.data["verdict"] = "PENDING"
        final.data["current_run"] = "NONE"


def _cascade_block(
    doc: PlanDocument,
    target: EntityBlock | None,
    reason: str,
    conditions: list[str] | None = None,
) -> None:
    conditions = conditions or ["차단 원인을 해소하고 검증한다."]
    old_plan_status = doc.metadata.get("status")
    if old_plan_status != "BLOCKED":
        doc.metadata["blocked_from"] = old_plan_status
    doc.metadata["status"] = "BLOCKED"
    doc.metadata["blocked_reason"] = reason
    doc.metadata["unblock_conditions"] = conditions
    if target is None:
        return
    if target.kind in {"task", "test", "phase"}:
        old = target.data.get("status")
        if old != "BLOCKED":
            target.data["blocked_from"] = old
        target.data["status"] = "BLOCKED"
        target.data["blocked_reason"] = reason
        target.data["unblock_conditions"] = conditions
    elif target.kind == "qa":
        if target.data.get("blocked_from") in {None, "NONE"}:
            target.data["blocked_from"] = target.data.get("status")
        target.data["blocked_reason"] = reason
        target.data["unblock_conditions"] = conditions
    if target.phase_id:
        phase = doc.entity(target.phase_id)
        if phase.data.get("status") != "BLOCKED":
            phase.data["blocked_from"] = phase.data.get("status")
        phase.data["status"] = "BLOCKED"
        phase.data["blocked_reason"] = reason
        phase.data["unblock_conditions"] = conditions


def _clear_block(doc: PlanDocument, payload: dict[str, Any]) -> None:
    entity_ids = list(payload.get("entity_ids", []))
    phase_ids = list(payload.get("phase_ids", []))
    for field, values in (("entity_ids", entity_ids), ("phase_ids", phase_ids)):
        if (
            any(not _is_nonempty_string(item) for item in values)
            or len(values) != len(set(values))
        ):
            raise PlanError("EVENT_PAYLOAD_INVALID", f"{field} must be a unique string list")
    entities = [doc.entity(entity_id) for entity_id in entity_ids]
    phases = [doc.entity(phase_id) for phase_id in phase_ids]
    if any(block.kind != "phase" for block in phases):
        raise PlanError("EVENT_PAYLOAD_INVALID", "phase_ids may contain only Phase IDs")
    if any(block.kind == "phase" and block.entity_id in set(phase_ids) for block in entities):
        raise PlanError("EVENT_PAYLOAD_INVALID", "A Phase may not appear in both entity_ids and phase_ids")
    blocked_entities = {
        block.entity_id
        for block in doc.blocks
        if block.kind != "phase"
        and (
            block.data.get("status") == "BLOCKED"
            or block.data.get("blocked_from") not in {None, "NONE"}
        )
    }
    blocked_phases = {
        block.entity_id
        for block in doc.blocks_of("phase")
        if (
            block.data.get("status") == "BLOCKED"
            or block.data.get("blocked_from") not in {None, "NONE"}
        )
    }
    if set(entity_ids) != blocked_entities or set(phase_ids) != blocked_phases:
        raise PlanError(
            "GUARD_FAILED",
            "BLOCK_CLEARED must include the complete blocked entity/Phase cascade",
        )
    for block in [*entities, *phases]:
        if block.data.get("status") != "BLOCKED" and block.data.get("blocked_from") in {None, "NONE"}:
            raise PlanError(
                "EVENT_FROM_MISMATCH",
                f"{block.entity_id} is not blocked",
                entity=block.entity_id,
            )
    if doc.metadata.get("blocked_from") in {None, "NONE"}:
        raise PlanError("GUARD_FAILED", "BLOCKED Plan has no blocked_from state")

    for entity_id in entity_ids:
        block = doc.entity(entity_id)
        if block.kind == "task":
            block.data["status"] = "REWORK"
            block.data["current_run"] = "NONE"
            block.data["worker_tier"] = "UNASSIGNED"
            block.data["assigned_model"] = "UNASSIGNED"
        elif block.kind == "test":
            block.data["status"] = "PENDING"
            block.data["current_run"] = "NONE"
            block.data["actual"] = "NOT_RUN"
            block.data["evidence"] = "NONE"
        elif block.kind == "qa":
            block.data["status"] = "PENDING"
            block.data["verdict"] = "PENDING"
            block.data["current_run"] = "NONE"
        else:
            block.data["status"] = block.data.get("blocked_from", "PENDING")
        block.data["blocked_from"] = "NONE"
        block.data["blocked_reason"] = "NONE"
        block.data["unblock_conditions"] = []
    for phase_id in phase_ids:
        phase = doc.entity(phase_id)
        phase.data["status"] = phase.data.get("blocked_from", "IN_PROGRESS")
        phase.data["blocked_from"] = "NONE"
        phase.data["blocked_reason"] = "NONE"
        phase.data["unblock_conditions"] = []
    if doc.metadata.get("status") == "BLOCKED":
        doc.metadata["status"] = doc.metadata.get("blocked_from", "READY")
    doc.metadata["blocked_from"] = "NONE"
    doc.metadata["blocked_reason"] = "NONE"
    doc.metadata["unblock_conditions"] = []


def _accept_risk(
    doc: PlanDocument,
    payload: dict[str, Any],
    checked_ref: Any,
) -> None:
    risk_id = payload.get("risk_id")
    reason = payload.get("reason")
    if not _is_nonempty_string(risk_id) or not _is_nonempty_string(reason):
        raise PlanError("EVENT_PAYLOAD_INVALID", "risk_id and reason are required")
    if any(item.get("risk_id") == risk_id for item in doc.metadata.get("residual_risks", []) or []):
        raise PlanError("EVENT_PAYLOAD_INVALID", f"Duplicate risk_id: {risk_id}")
    finding_ref = payload.get("finding_ref")
    finding = next(
        (item for item in doc.metadata.get("finding_ledger", []) or [] if item.get("finding_ref") == finding_ref),
        None,
    )
    if not finding or finding.get("status") != "OPEN":
        raise PlanError("GUARD_FAILED", "RISK_ACCEPTED requires an OPEN finding")
    risk = {
        "risk_id": risk_id,
        "finding_ref": finding_ref,
        "decision": "ACCEPTED",
        "reason": reason,
        "approved_at": payload.get("approved_at", now_iso()),
        "approval_evidence": checked_ref(payload.get("approval_evidence")),
    }
    doc.metadata.setdefault("residual_risks", []).append(risk)
    finding["status"] = "ACCEPTED_RISK"
    finding["resolved_by"] = risk["risk_id"]


class PlanFileLock:
    """Crash-safe local advisory lock backed by a persistent inode."""

    def __init__(
        self,
        path: Path,
        *,
        expected_sha256: str | None = None,
        timeout: float = 30.0,
        stale_seconds: float = 600.0,
    ):
        self.path = path
        self.expected_sha256 = expected_sha256
        self.timeout = timeout
        self.stale_seconds = stale_seconds
        self.acquired = False
        self.token = secrets.token_hex(16)
        self.identity: tuple[int, int] | None = None
        self.descriptor: int | None = None

    def __enter__(self) -> "PlanFileLock":
        if fcntl is None:
            raise PlanError("LOCK_UNAVAILABLE", "POSIX fcntl.flock support is required")
        deadline = time.monotonic() + self.timeout
        payload = {
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "created_at": now_iso(),
            "expected_document_sha256": self.expected_sha256,
            "token": self.token,
            "state": "HELD",
        }
        while True:
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                descriptor_stat = os.fstat(fd)
                path_stat = self.path.lstat()
                self.identity = (descriptor_stat.st_dev, descriptor_stat.st_ino)
                if self.identity != (path_stat.st_dev, path_stat.st_ino):
                    raise OSError("Plan lock path changed while acquiring")
                encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                offset = 0
                while offset < len(encoded):
                    offset += os.write(fd, encoded[offset:])
                os.fsync(fd)
                _fsync_directory(self.path.parent)
                self.descriptor = fd
                self.acquired = True
                return self
            except BlockingIOError:
                os.close(fd)
                if time.monotonic() >= deadline:
                    raise PlanError("LOCK_TIMEOUT", f"Timed out waiting for lock: {self.path}")
                time.sleep(0.1)
            except Exception:
                os.close(fd)
                raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        descriptor = self.descriptor
        self.descriptor = None
        self.acquired = False
        if descriptor is None:
            return
        try:
            payload = json.dumps(
                {
                    "host": socket.gethostname(),
                    "pid": os.getpid(),
                    "released_at": now_iso(),
                    "token": self.token,
                    "state": "RELEASED",
                },
                sort_keys=True,
            ).encode("utf-8")
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
        finally:
            assert fcntl is not None
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def write_plan_atomic(
    doc: PlanDocument,
    *,
    expected_sha256: str,
    dry_run: bool = False,
) -> str:
    original = doc.path.read_text(encoding="utf-8")
    actual_sha = text_sha256(original)
    if actual_sha != expected_sha256:
        raise PlanError("CAS_MISMATCH", f"Expected document SHA {expected_sha256}, got {actual_sha}")
    rendered = doc.render()
    structural = validate_structural(parse_plan(doc.path, text=rendered))
    if structural:
        raise structural[0]
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=str(doc.path),
            tofile=str(doc.path),
        )
    )
    if dry_run:
        return diff

    lock_path = doc.path.with_suffix(doc.path.suffix + ".lock")
    with PlanFileLock(lock_path, expected_sha256=expected_sha256):
        current = doc.path.read_text(encoding="utf-8")
        if text_sha256(current) != expected_sha256:
            raise PlanError("CAS_MISMATCH", "Plan changed while waiting for the lock")
        plan_id = str(doc.metadata.get("plan_id"))
        history_dir = doc.path.parent / "evidence" / plan_id / "state-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_name = (
            f"{int(doc.metadata.get('document_version', 0)):06d}-"
            f"{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{expected_sha256[:16]}.md"
        )
        history_path = history_dir / history_name
        history_path.write_text(current, encoding="utf-8")
        with history_path.open("rb") as handle:
            os.fsync(handle.fileno())

        fd, temp_name = tempfile.mkstemp(prefix=f".{doc.path.name}.", dir=doc.path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, doc.path)
            directory_fd = os.open(doc.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temp_path.unlink(missing_ok=True)
    return diff


def _apply_event_atomic_inner(
    plan_path: str | Path,
    event: dict[str, Any],
    *,
    expected_sha256: str,
    expected_document_version: int,
    dry_run: bool = False,
    verify_evidence: bool = True,
) -> tuple[PlanDocument, str]:
    """Apply one Lead event with digest/version CAS and lock-scoped evidence checks."""

    path = Path(plan_path).expanduser().resolve()
    original = path.read_text(encoding="utf-8")
    if text_sha256(original) != expected_sha256:
        raise PlanError("CAS_MISMATCH", "Expected document SHA does not match the plan")
    preview = parse_plan(path, text=original)
    if preview.metadata.get("document_version") != expected_document_version:
        raise PlanError(
            "CAS_MISMATCH",
            f"Expected document_version {expected_document_version}, "
            f"got {preview.metadata.get('document_version')}",
        )
    apply_event(preview, event, verify_evidence=verify_evidence)
    rendered = preview.render()
    rendered_doc = parse_plan(path, text=rendered)
    errors = validate_structural(rendered_doc)
    if not errors and rendered_doc.metadata.get("status") in {"READY", "IN_PROGRESS", "QA"}:
        errors = validate_executable(rendered_doc, check_evidence=verify_evidence)
    if errors:
        raise errors[0]
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )
    if dry_run:
        return preview, diff

    phase_commit = verify_evidence and event.get("event") == "PHASE_APPROVED"
    source_state_gate = verify_evidence and event.get("event") in {
        "PLAN_READY",
        "EXECUTION_STARTED",
        "PHASE_APPROVED",
        "PLAN_APPROVED",
    }
    source_lock = (
        IntegrationLock(project_root_for(path))
        if source_state_gate
        else contextlib.nullcontext()
    )
    evidence_lock_root = (
        path.parent
        / "evidence"
        / str(preview.metadata.get("plan_id"))
    )
    evidence_lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with source_lock, IntegrationLock(
        evidence_lock_root,
        lock_name=".control-plane.lock",
    ):
        with PlanFileLock(lock_path, expected_sha256=expected_sha256):
            current = path.read_text(encoding="utf-8")
            if text_sha256(current) != expected_sha256:
                raise PlanError("CAS_MISMATCH", "Plan changed while waiting for the lock")
            current_doc = parse_plan(path, text=current)
            if current_doc.metadata.get("document_version") != expected_document_version:
                raise PlanError("CAS_MISMATCH", "document_version changed while waiting for the lock")

            # Re-apply while both source and Plan locks are held for PHASE_APPROVED.
            apply_event(current_doc, event, verify_evidence=verify_evidence)
            locked_rendered = current_doc.render()
            locked_doc = parse_plan(path, text=locked_rendered)
            locked_errors = validate_structural(locked_doc)
            if not locked_errors and locked_doc.metadata.get("status") in {"READY", "IN_PROGRESS", "QA"}:
                locked_errors = validate_executable(locked_doc, check_evidence=verify_evidence)
            if locked_errors:
                raise locked_errors[0]

            commit_marker_path: Path | None = None
            commit_marker: dict[str, Any] | None = None
            if phase_commit:
                payload = event["payload"]
                journal_ref = payload["integration_journal"]
                journal_path = (project_root_for(path) / str(journal_ref["path"])).resolve()
                commit_marker_path = journal_path.parent / "COMMITTED.json"
                commit_marker = {
                    "schema": "codex-integration-commit/v1",
                    "status": "COMMITTING",
                    "plan_id": current_doc.metadata.get("plan_id"),
                    "phase_id": payload.get("phase_id"),
                    "journal_sha256": journal_ref.get("sha256"),
                    "pre_plan_sha256": expected_sha256,
                    "pre_document_version": expected_document_version,
                    "post_plan_sha256": text_sha256(locked_rendered),
                    "post_document_version": current_doc.metadata.get("document_version"),
                    "created_at": now_iso(),
                }
                write_manifest_exclusive(commit_marker_path, commit_marker)

            plan_id = str(current_doc.metadata.get("plan_id"))
            history_dir = path.parent / "evidence" / plan_id / "state-history"
            history_dir.mkdir(parents=True, exist_ok=True)
            history_name = (
                f"{expected_document_version:06d}-"
                f"{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{expected_sha256[:16]}.md"
            )
            history_path = history_dir / history_name
            history_path.write_text(current, encoding="utf-8")
            with history_path.open("rb") as handle:
                os.fsync(handle.fileno())

            fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(locked_rendered)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                temp_path.unlink(missing_ok=True)

            if commit_marker_path is not None and commit_marker is not None:
                commit_marker["status"] = "COMMITTED"
                commit_marker["committed_at"] = now_iso()
                update_json_atomic(commit_marker_path, commit_marker)
    return current_doc, diff


def apply_event_atomic(
    plan_path: str | Path,
    event: dict[str, Any],
    *,
    expected_sha256: str,
    expected_document_version: int,
    dry_run: bool = False,
    verify_evidence: bool = True,
) -> tuple[PlanDocument, str]:
    """Apply an event and compensate a failed PHASE_APPROVED source integration."""

    try:
        return _apply_event_atomic_inner(
            plan_path,
            event,
            expected_sha256=expected_sha256,
            expected_document_version=expected_document_version,
            dry_run=dry_run,
            verify_evidence=verify_evidence,
        )
    except Exception as original_error:
        if (
            dry_run
            or not verify_evidence
            or event.get("event") != "PHASE_APPROVED"
        ):
            raise

        path = Path(plan_path).expanduser().resolve()
        # If replacement already committed before a durability error surfaced, never
        # compensate the source behind an approved Plan. Report the uncertain fsync
        # outcome and leave both postimages intact for reconciliation.
        current: PlanDocument | None = None
        already_approved = False
        try:
            current = parse_plan(path)
            phase_id = str((event.get("payload") or {}).get("phase_id", ""))
            already_approved = bool(
                phase_id
                and current.entity(phase_id).data.get("status") == "DONE"
            )
        except PlanError:
            pass
        except (OSError, ValueError):
            pass
        if already_approved:
            raise original_error

        payload = event.get("payload")
        journal_ref = payload.get("integration_journal") if isinstance(payload, dict) else None
        reference_errors = validate_evidence_reference(journal_ref, project_root=project_root_for(path))
        if reference_errors:
            raise PlanError(
                "INTEGRATION_ROLLBACK_FAILED",
                f"Plan event failed ({original_error}); rollback journal is invalid: "
                f"{reference_errors[0].message}",
            ) from original_error
        journal_path = (project_root_for(path) / str(journal_ref["path"])).resolve()
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as journal_error:
            raise PlanError(
                "INTEGRATION_ROLLBACK_FAILED",
                f"Plan event failed ({original_error}); rollback journal cannot be read: {journal_error}",
            ) from original_error
        payload = event.get("payload") or {}
        if (
            journal.get("schema") != "codex-integration-journal/v1"
            or journal.get("status") not in {"PREPARED", "INTEGRATED"}
            or Path(str(journal.get("plan_file"))).resolve() != path
            or journal.get("phase_id") != payload.get("phase_id")
            or journal.get("expected_plan_sha256") != expected_sha256
            or journal.get("expected_document_version") != expected_document_version
            or (
                current is not None
                and journal.get("plan_id") != current.metadata.get("plan_id")
            )
        ):
            raise PlanError(
                "INTEGRATION_ROLLBACK_FAILED",
                f"Plan event failed ({original_error}); rollback journal is not bound to this Plan event",
            ) from original_error
        try:
            rollback_integration(journal_path)
        except (OSError, ValueError, WorkspaceGuardError, json.JSONDecodeError) as rollback_error:
            blocked_result = "Plan could not be marked BLOCKED"
            try:
                latest_text = path.read_text(encoding="utf-8")
                latest_doc = parse_plan(path, text=latest_text)
                if latest_doc.metadata.get("status") != "COMPLETED":
                    _apply_event_atomic_inner(
                        path,
                        {
                            "event": "ENTITY_BLOCKED",
                            "payload": {
                                "entity_id": "PLAN",
                                "reason": f"Source integration rollback failed: {rollback_error}",
                                "unblock_conditions": [
                                    "source와 integration journal을 수동 대조한다.",
                                    "보존할 사용자 변경을 확인한 뒤 source state를 복구한다.",
                                ],
                            },
                        },
                        expected_sha256=text_sha256(latest_text),
                        expected_document_version=int(
                            latest_doc.metadata.get("document_version", -1)
                        ),
                        verify_evidence=False,
                    )
                    blocked_result = "Plan was marked BLOCKED"
            except (OSError, ValueError, PlanError) as block_error:
                blocked_result = f"Plan BLOCKED update also failed: {block_error}"
            raise PlanError(
                "INTEGRATION_ROLLBACK_FAILED",
                f"Plan event failed ({original_error}); source rollback also failed: "
                f"{rollback_error}. {blocked_result}",
            ) from original_error
        raise PlanError(
            "PLAN_EVENT_ROLLED_BACK",
            f"Plan event failed and source integration was rolled back: {original_error}",
        ) from original_error
