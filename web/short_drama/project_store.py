# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""
Persistence and validation for Short Drama — 项目 (on-disk projects + index).
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_JSON = "project.json"
INDEX_SUBPATH = Path("data") / "short_drama" / "projects_index.json"
SCHEMA_VERSION = 1

# Avoid creating projects directly on a few system directory roots (exact match only)
_FORBIDDEN_EXACT = frozenset(
    {
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/lib",
        "/lib64",
        "/proc",
        "/sys",
        "/sbin",
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _index_path() -> Path:
    return _repo_root() / INDEX_SUBPATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ProjectMeta:
    name: str
    description: str
    root_path: str
    created_at: str
    updated_at: str
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], root_path: str) -> ProjectMeta:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            root_path=str(data.get("root_path", root_path)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            tags=list(data.get("tags") or []),
        )


def validate_linux_absolute_path(raw: str) -> tuple[bool, str, Path | None]:
    """
    Validate Linux-style absolute path (must start with /, no backslashes, safe resolved path).
    Returns (ok, error_message, resolved_path_or_none).
    """
    if raw is None:
        return False, "empty", None
    s = raw.strip()
    if not s:
        return False, "empty", None
    if "\\" in s:
        return False, "backslash", None
    if "\x00" in s:
        return False, "null_byte", None
    if not s.startswith("/"):
        return False, "not_absolute", None
    if re.search(r"[\r\n]", s):
        return False, "newline", None

    try:
        p = Path(s).expanduser().resolve()
    except (OSError, RuntimeError):
        return False, "resolve_failed", None

    resolved = str(p)
    if resolved in _FORBIDDEN_EXACT:
        return False, "forbidden_root", None

    return True, "", p


def _read_index_paths() -> list[str]:
    path = _index_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if isinstance(item, str) and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _write_index_paths(paths: list[str]) -> None:
    idx = _index_path()
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(json.dumps(paths, ensure_ascii=False, indent=2), encoding="utf-8")


def _project_json_path(root: Path) -> Path:
    return root / PROJECT_JSON


def load_project_at(root: Path) -> ProjectMeta | None:
    pj = _project_json_path(root)
    if not pj.is_file():
        return None
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return ProjectMeta.from_dict(data, str(root.resolve()))


def list_projects() -> list[ProjectMeta]:
    metas: list[ProjectMeta] = []
    stale: list[str] = []
    for path_str in _read_index_paths():
        root = Path(path_str)
        meta = load_project_at(root)
        if meta is None:
            stale.append(path_str)
            continue
        metas.append(meta)
    if stale:
        kept = [p for p in _read_index_paths() if p not in stale]
        _write_index_paths(kept)
    metas.sort(key=lambda m: m.updated_at or m.created_at, reverse=True)
    return metas


def _add_index_path(path_str: str) -> None:
    paths = _read_index_paths()
    if path_str not in paths:
        paths.append(path_str)
        _write_index_paths(paths)


def _replace_index_resolved(old_resolved: str, new_resolved: str) -> None:
    """Swap index entry from old project root to new (resolved paths)."""
    old_r = str(Path(old_resolved).resolve())
    new_r = str(Path(new_resolved).resolve())
    paths = _read_index_paths()
    out: list[str] = []
    seen: set[str] = set()
    for p in paths:
        pr = str(Path(p).resolve())
        if pr == old_r:
            if new_r not in seen:
                out.append(new_r)
                seen.add(new_r)
        else:
            if pr not in seen:
                out.append(p)
                seen.add(pr)
    _write_index_paths(out)


def create_project(name: str, description: str, path_raw: str) -> tuple[bool, str]:
    """Create project directory + project.json and register in index."""
    name = (name or "").strip()
    if not name:
        return False, "name_empty"
    ok, err_key, resolved = validate_linux_absolute_path(path_raw)
    if not ok or resolved is None:
        return False, err_key

    root = resolved
    pj = _project_json_path(root)
    if pj.exists():
        return False, "already_exists"

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False, "mkdir_failed"

    now = _now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "description": (description or "").strip(),
        "root_path": str(root),
        "created_at": now,
        "updated_at": now,
        "tags": [],
    }
    try:
        pj.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        try:
            if root.exists() and not any(root.iterdir()):
                root.rmdir()
        except OSError:
            pass
        return False, "write_failed"

    _add_index_path(str(root))
    return True, ""


def update_project(
    root_path_str: str,
    name: str,
    description: str,
    new_root_path_raw: str,
) -> tuple[bool, str]:
    """
    Update project name/description and optionally move project directory when path changes.
    Name and path are decoupled; move only if resolved new path differs from current root.
    """
    root = Path(root_path_str)
    meta = load_project_at(root)
    if meta is None:
        return False, "project_not_found"
    name = (name or "").strip()
    if not name:
        return False, "name_empty"

    ok, err_key, new_root = validate_linux_absolute_path(new_root_path_raw)
    if not ok or new_root is None:
        return False, err_key

    old_root = root.resolve()
    new_root = new_root.resolve()

    if new_root == old_root:
        target_root = old_root
    else:
        if new_root.exists():
            return False, "move_target_exists"
        try:
            new_root.relative_to(old_root)
            return False, "move_into_self"
        except ValueError:
            pass
        parent = new_root.parent
        if not parent.is_dir():
            return False, "move_parent_missing"
        try:
            shutil.move(str(old_root), str(new_root))
        except OSError:
            return False, "move_failed"
        target_root = new_root.resolve()
        _replace_index_resolved(str(old_root), str(target_root))

    now = _now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "description": (description or "").strip(),
        "root_path": str(target_root),
        "created_at": meta.created_at,
        "updated_at": now,
        "tags": meta.tags,
    }
    try:
        _project_json_path(target_root).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        return False, "write_failed"
    return True, ""


def remove_from_index_only(root_path_str: str) -> None:
    paths = [p for p in _read_index_paths() if p != root_path_str]
    _write_index_paths(paths)


def delete_project_directory(root_path_str: str) -> tuple[bool, str]:
    """Remove from index and delete project directory (must contain our project.json)."""
    root = Path(root_path_str)
    pj = _project_json_path(root)
    if not pj.is_file():
        remove_from_index_only(root_path_str)
        return False, "project_not_found"
    try:
        shutil.rmtree(root)
    except OSError:
        return False, "rmtree_failed"
    remove_from_index_only(root_path_str)
    return True, ""
