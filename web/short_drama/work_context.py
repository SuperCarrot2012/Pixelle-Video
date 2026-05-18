# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Short drama — active project (global work path) in Streamlit session state.

角色 / 道具 / 场景 / 分镜 等子页通过 get_work_path() 读取当前项目根目录。
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from web.short_drama.project_store import PROJECT_JSON, load_project_at

WORK_PATH_KEY = "short_drama_work_path"
WORK_NAME_KEY = "short_drama_work_name"
SESSION_HYDRATED_KEY = "short_drama_active_hydrated"

# Resource subdirectories under project root (created on load)
RESOURCE_DIRS = ("roles", "props", "scenes", "storyboard")

# Persistence file (relative to repo root) so the active project survives
# browser refreshes and Streamlit restarts.
_ACTIVE_FILE_SUBPATH = Path("data") / "short_drama" / "active_project.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _active_file_path() -> Path:
    return _repo_root() / _ACTIVE_FILE_SUBPATH


def _persist_active_to_disk(root_path: str | None) -> None:
    f = _active_file_path()
    try:
        if root_path is None:
            if f.is_file():
                f.unlink()
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps({"root_path": root_path}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_persisted_active() -> str | None:
    f = _active_file_path()
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("root_path")
    return raw if isinstance(raw, str) and raw else None


def _resolved(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _hydrate_from_disk_once() -> None:
    """Restore the active project from disk into session state on first access."""
    if st.session_state.get(SESSION_HYDRATED_KEY):
        return
    st.session_state[SESSION_HYDRATED_KEY] = True
    if st.session_state.get(WORK_PATH_KEY):
        return
    persisted = _load_persisted_active()
    if not persisted:
        return
    root = Path(persisted)
    if not (root / PROJECT_JSON).is_file():
        _persist_active_to_disk(None)
        return
    meta = load_project_at(root)
    if meta is None:
        _persist_active_to_disk(None)
        return
    st.session_state[WORK_PATH_KEY] = _resolved(persisted)
    st.session_state[WORK_NAME_KEY] = meta.name


def get_work_path() -> str | None:
    """Current project root (Linux absolute path), or None if none loaded."""
    _hydrate_from_disk_once()
    raw = st.session_state.get(WORK_PATH_KEY)
    if not raw:
        return None
    p = Path(raw)
    if not (p / PROJECT_JSON).is_file():
        clear_active_project()
        return None
    return _resolved(raw)


def get_work_name() -> str | None:
    _hydrate_from_disk_once()
    return st.session_state.get(WORK_NAME_KEY)


def is_active_project(root_path: str) -> bool:
    active = get_work_path()
    if not active:
        return False
    try:
        return _resolved(root_path) == _resolved(active)
    except (OSError, RuntimeError):
        return False


def clear_active_project() -> None:
    st.session_state.pop(WORK_PATH_KEY, None)
    st.session_state.pop(WORK_NAME_KEY, None)
    _persist_active_to_disk(None)


def _ensure_resource_dirs(root: Path) -> None:
    for name in RESOURCE_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)


def activate_project(root_path: str) -> bool:
    """
    Set global work path and ensure project + resource directories exist.
    Persists across browser refreshes via an on-disk pointer file.
    Returns False if project.json is missing.
    """
    root = Path(root_path).expanduser().resolve()
    meta = load_project_at(root)
    if meta is None:
        return False
    _ensure_resource_dirs(root)
    resolved = str(root)
    st.session_state[WORK_PATH_KEY] = resolved
    st.session_state[WORK_NAME_KEY] = meta.name
    st.session_state[SESSION_HYDRATED_KEY] = True
    _persist_active_to_disk(resolved)
    return True


def sync_active_project_after_move(old_path: str, new_path: str) -> None:
    """If the loaded project was moved, update session + persisted file to new path."""
    if not st.session_state.get(WORK_PATH_KEY):
        return
    try:
        if _resolved(old_path) == _resolved(st.session_state[WORK_PATH_KEY]):
            new_resolved = _resolved(new_path)
            st.session_state[WORK_PATH_KEY] = new_resolved
            meta = load_project_at(Path(new_path))
            if meta:
                st.session_state[WORK_NAME_KEY] = meta.name
            _persist_active_to_disk(new_resolved)
    except (OSError, RuntimeError):
        pass


def clear_active_project_if_matches(root_path: str) -> None:
    if is_active_project(root_path):
        clear_active_project()


def resource_dir(resource: str) -> Path | None:
    """
    Subpath under active project, e.g. resource='roles' -> .../roles
    """
    base = get_work_path()
    if not base or resource not in RESOURCE_DIRS:
        return None
    return Path(base) / resource
