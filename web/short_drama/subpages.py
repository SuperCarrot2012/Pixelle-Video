# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Stub subpages — 道具 / 场景 / 分镜.

The 角色 (Roles) subpage has its own module: ``web.short_drama.role_page``.
Each subpage is gated by the global active project (see ``work_context``).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from web.i18n import tr
from web.short_drama.work_context import get_work_path


def _render_work_path_gate() -> bool:
    """Return True if a project is loaded; otherwise show hint and return False."""
    if get_work_path():
        return True
    st.info(tr("short_drama.work.no_project"))
    return False


def render_props_subpage(_pixelle_video: Any) -> None:
    """道具 — 待实现"""
    if not _render_work_path_gate():
        return
    st.caption(tr("short_drama.work.using_path", path=get_work_path()))


def render_scene_subpage(_pixelle_video: Any) -> None:
    """场景 — 待实现"""
    if not _render_work_path_gate():
        return
    st.caption(tr("short_drama.work.using_path", path=get_work_path()))


def render_storyboard_subpage(_pixelle_video: Any) -> None:
    """分镜 — 待实现"""
    if not _render_work_path_gate():
        return
    st.caption(tr("short_drama.work.using_path", path=get_work_path()))
