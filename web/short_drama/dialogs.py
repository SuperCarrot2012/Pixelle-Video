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
Streamlit dialog wrappers for Short Drama project / role actions.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from web.i18n import tr
from web.short_drama.errors import map_error
from web.short_drama import role_store
from web.short_drama.project_store import (
    delete_project_directory,
    load_project_at,
    update_project,
)
from web.short_drama.ui_helpers import dialog_widget_suffix
from web.short_drama.work_context import (
    clear_active_project_if_matches,
    sync_active_project_after_move,
)


@st.dialog(tr("short_drama.project.edit_title"))
def project_edit_dialog(root_path: str) -> None:
    """编辑项目（弹窗）"""
    meta = load_project_at(Path(root_path))
    if meta is None:
        st.error(map_error("project_not_found"))
        if st.button(tr("short_drama.project.cancel"), key="sd_edit_dlg_close_missing"):
            st.rerun()
        return
    suf = dialog_widget_suffix(root_path)
    with st.form(f"short_drama_edit_dlg_form_{suf}"):
        name = st.text_input(
            tr("short_drama.project.name"),
            value=meta.name,
            key=f"short_drama_edit_dlg_name_{suf}",
        )
        desc = st.text_area(
            tr("short_drama.project.description"),
            value=meta.description,
            height=160,
            key=f"short_drama_edit_dlg_desc_{suf}",
        )
        path_raw = st.text_input(
            tr("short_drama.project.path"),
            value=meta.root_path,
            placeholder=tr("short_drama.project.path_placeholder"),
            help=tr("short_drama.project.path_edit_help"),
            key=f"short_drama_edit_dlg_path_{suf}",
        )
        _, c_save, c_cancel = st.columns([3, 1, 1])
        with c_save:
            submitted = st.form_submit_button(
                tr("short_drama.project.save"), type="primary", width="stretch"
            )
        with c_cancel:
            cancelled = st.form_submit_button(
                tr("short_drama.project.cancel"), width="stretch"
            )
    if cancelled:
        st.rerun()
    if submitted:
        path_effective = (path_raw or "").strip() or meta.root_path
        ok, err = update_project(str(root_path), name, desc, path_effective)
        if ok:
            path_effective = (path_raw or "").strip() or meta.root_path
            try:
                if str(Path(path_effective).resolve()) != str(Path(root_path).resolve()):
                    sync_active_project_after_move(str(root_path), path_effective)
            except (OSError, RuntimeError):
                pass
            st.toast(tr("short_drama.project.update_success"), icon="✅")
            st.rerun()
        else:
            st.error(map_error(err))


@st.dialog(tr("short_drama.project.delete_confirm_title"))
def project_delete_dialog(root_path: str) -> None:
    """删除项目确认（弹窗）"""
    st.markdown(tr("short_drama.project.delete_confirm_body", path=root_path))
    suf = dialog_widget_suffix(root_path)
    _, c_yes, c_no = st.columns([3, 1, 1])
    if c_yes.button(
        tr("short_drama.project.delete_confirm_yes"),
        type="primary",
        key=f"sd_delete_dlg_yes_{suf}",
        width="stretch",
    ):
        ok, err = delete_project_directory(str(root_path))
        if ok:
            clear_active_project_if_matches(str(root_path))
            st.toast(tr("short_drama.project.delete_success"), icon="✅")
            st.rerun()
        else:
            st.error(map_error(err))
    if c_no.button(
        tr("short_drama.project.cancel"),
        key=f"sd_delete_dlg_no_{suf}",
        width="stretch",
    ):
        st.rerun()


_SK_EDITING_ROLE = "sd_role_editing_en"


@st.dialog(tr("short_drama.role.delete_confirm_title"))
def role_delete_dialog(english_name: str, display_name: str) -> None:
    """删除角色确认（弹窗）"""
    cn = (display_name or english_name).strip()
    st.markdown(
        tr(
            "short_drama.role.delete_confirm_body",
            cn=cn,
            en=english_name,
        )
    )
    suf = dialog_widget_suffix(english_name)
    _, c_yes, c_no = st.columns([3, 1, 1])
    if c_yes.button(
        tr("short_drama.project.delete_confirm_yes"),
        type="primary",
        key=f"sd_role_delete_dlg_yes_{suf}",
        width="stretch",
    ):
        ok, err = role_store.delete_role(english_name)
        if ok:
            if st.session_state.get(_SK_EDITING_ROLE) == english_name:
                st.session_state.pop(_SK_EDITING_ROLE, None)
            st.toast(
                tr(
                    "short_drama.role.delete_success",
                    name=cn or english_name,
                ),
                icon="✅",
            )
            st.rerun()
        else:
            st.error(map_error(err))
    if c_no.button(
        tr("short_drama.project.cancel"),
        key=f"sd_role_delete_dlg_no_{suf}",
        width="stretch",
    ):
        st.rerun()
