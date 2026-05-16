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
Project subpage rendering: new-project form, active-project banner,
project cards grid (load / edit / delete actions per card).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from web.i18n import tr
from web.short_drama.dialogs import project_delete_dialog, project_edit_dialog
from web.short_drama.errors import map_project_error
from web.short_drama.project_store import (
    ProjectMeta,
    create_project,
    list_projects,
)
from web.short_drama.ui_helpers import (
    PROJECT_CARDS_PER_ROW,
    PROJECT_CARD_PATH_DISPLAY_LEN,
    project_card_token,
    truncate_middle,
)
from web.short_drama.work_context import (
    activate_project,
    get_work_name,
    get_work_path,
    is_active_project,
)


def render_project_subpage(_pixelle_video: Any) -> None:
    """项目：新建 / 加载（卡片网格）"""
    st.markdown(f"#### {tr('short_drama.project.section.new')}")
    _render_new_project_form()
    st.divider()
    st.markdown(f"#### {tr('short_drama.project.section.load')}")
    if st.session_state.pop("short_drama_load_toast", None):
        st.toast(tr("short_drama.project.load_success"), icon="✅")
    projects = list_projects()
    _render_active_project_banner()
    _render_project_cards_grid(projects)


def _render_new_project_form() -> None:
    with st.form("short_drama_new_project_form"):
        name = st.text_input(tr("short_drama.project.name"), key="short_drama_new_name")
        desc = st.text_area(
            tr("short_drama.project.description"),
            height=120,
            key="short_drama_new_desc",
        )
        path_raw = st.text_input(
            tr("short_drama.project.path"),
            placeholder=tr("short_drama.project.path_placeholder"),
            help=tr("short_drama.project.path_help"),
            key="short_drama_new_path",
        )
        submitted = st.form_submit_button(tr("short_drama.project.create"), type="primary")
    if not submitted:
        return
    ok, err_key = create_project(name, desc, path_raw or "")
    if ok:
        st.toast(tr("short_drama.project.create_success"), icon="✅")
        st.rerun()
    else:
        st.error(map_project_error(err_key))


def _render_active_project_banner() -> None:
    work_path = get_work_path()
    if not work_path:
        st.caption(tr("short_drama.work.hint_select"))
        return
    name = get_work_name() or work_path
    st.info(tr("short_drama.work.current", name=name, path=work_path))


def _render_project_cards_grid(projects: list[ProjectMeta]) -> None:
    if not projects:
        st.info(tr("short_drama.project.empty_list"))
        return
    n = PROJECT_CARDS_PER_ROW
    for row_start in range(0, len(projects), n):
        cols = st.columns(n, gap="medium")
        for j in range(n):
            idx = row_start + j
            if idx >= len(projects):
                continue
            proj = projects[idx]
            with cols[j]:
                _render_one_project_card(
                    proj, idx, is_active_project(proj.root_path)
                )


def _render_one_project_card(
    proj: ProjectMeta, card_index: int, is_active: bool
) -> None:
    h = project_card_token(proj.root_path)
    with st.container(border=True):
        if is_active:
            st.success(
                f"✓ {tr('short_drama.project.loaded_badge')}",
                icon="📂",
            )

        st.subheader(proj.name)

        desc_raw = (proj.description or "").strip()
        if desc_raw:
            st.write(desc_raw)
        else:
            st.caption("—")

        ts = proj.updated_at or proj.created_at
        if ts:
            st.caption(f"🕒 {ts}")

        path_short = truncate_middle(
            proj.root_path, PROJECT_CARD_PATH_DISPLAY_LEN
        )
        st.caption(f"📁 {path_short}", help=proj.root_path)

        l_col, e_col, d_col = st.columns(3)
        with l_col:
            load_label = (
                tr("short_drama.project.loaded_badge")
                if is_active
                else tr("short_drama.project.load")
            )
            if st.button(
                f"📂 {load_label}",
                key=f"sd_load_{card_index}_{h}",
                disabled=is_active,
                width="stretch",
            ):
                if activate_project(proj.root_path):
                    st.session_state.short_drama_load_toast = True
                st.rerun()
        with e_col:
            if st.button(
                f"✏️ {tr('short_drama.project.edit')}",
                key=f"sd_edit_{card_index}_{h}",
                width="stretch",
            ):
                project_edit_dialog(proj.root_path)
        with d_col:
            if st.button(
                f"🗑️ {tr('short_drama.project.delete')}",
                key=f"sd_del_{card_index}_{h}",
                width="stretch",
            ):
                project_delete_dialog(proj.root_path)
