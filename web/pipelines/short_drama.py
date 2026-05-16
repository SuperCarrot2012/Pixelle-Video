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
Short Drama Pipeline UI — nested tabs: 项目 / 角色 / 道具 / 场景 / 分镜 (content TBD).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st

from web.i18n import tr
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.short_drama.project_store import (
    ProjectMeta,
    create_project,
    delete_project_directory,
    list_projects,
    load_project_at,
    update_project,
)
from web.short_drama.work_context import (
    activate_project,
    clear_active_project_if_matches,
    get_work_name,
    get_work_path,
    is_active_project,
    sync_active_project_after_move,
)

_ERR_I18N: dict[str, str] = {
    "name_empty": "short_drama.project.err.name_empty",
    "empty": "short_drama.project.err.path_empty",
    "backslash": "short_drama.project.err.path_backslash",
    "not_absolute": "short_drama.project.err.path_not_absolute",
    "null_byte": "short_drama.project.err.path_null",
    "newline": "short_drama.project.err.path_newline",
    "resolve_failed": "short_drama.project.err.path_resolve",
    "forbidden_root": "short_drama.project.err.path_forbidden",
    "already_exists": "short_drama.project.err.already_exists",
    "mkdir_failed": "short_drama.project.err.mkdir",
    "write_failed": "short_drama.project.err.write",
    "not_found": "short_drama.project.err.not_found",
    "rmtree_failed": "short_drama.project.err.rmtree",
    "move_target_exists": "short_drama.project.err.move_target_exists",
    "move_into_self": "short_drama.project.err.move_into_self",
    "move_parent_missing": "short_drama.project.err.move_parent_missing",
    "move_failed": "short_drama.project.err.move_failed",
}


def _map_project_error(err: str) -> str:
    key = _ERR_I18N.get(err, "short_drama.project.err.path_resolve")
    return tr(key)


_PROJECT_CARDS_PER_ROW = 4
_PROJECT_CARD_PATH_DISPLAY_LEN = 32


def _dialog_widget_suffix(root_path: str) -> str:
    return hashlib.md5(root_path.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _project_card_token(root_path: str) -> str:
    return hashlib.md5(root_path.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _truncate_middle(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    half = (max_len - 3) // 2
    return s[:half] + "..." + s[-(max_len - 3 - half):]


@st.dialog(tr("short_drama.project.edit_title"))
def _short_drama_project_edit_dialog(root_path: str) -> None:
    """编辑项目（弹窗）"""
    meta = load_project_at(Path(root_path))
    if meta is None:
        st.error(tr("short_drama.project.err.not_found"))
        if st.button(tr("short_drama.project.cancel"), key="sd_edit_dlg_close_missing"):
            st.rerun()
        return
    suf = _dialog_widget_suffix(root_path)
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
                tr("short_drama.project.save"), type="primary", use_container_width=True
            )
        with c_cancel:
            cancelled = st.form_submit_button(
                tr("short_drama.project.cancel"), use_container_width=True
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
            st.error(_map_project_error(err))


@st.dialog(tr("short_drama.project.delete_confirm_title"))
def _short_drama_project_delete_dialog(root_path: str) -> None:
    """删除项目确认（弹窗）"""
    st.markdown(tr("short_drama.project.delete_confirm_body", path=root_path))
    suf = _dialog_widget_suffix(root_path)
    _, c_yes, c_no = st.columns([3, 1, 1])
    if c_yes.button(
        tr("short_drama.project.delete_confirm_yes"),
        type="primary",
        key=f"sd_delete_dlg_yes_{suf}",
        use_container_width=True,
    ):
        ok, err = delete_project_directory(str(root_path))
        if ok:
            clear_active_project_if_matches(str(root_path))
            st.toast(tr("short_drama.project.delete_success"), icon="✅")
            st.rerun()
        else:
            st.error(_map_project_error(err))
    if c_no.button(
        tr("short_drama.project.cancel"),
        key=f"sd_delete_dlg_no_{suf}",
        use_container_width=True,
    ):
        st.rerun()


class ShortDramaPipelineUI(PipelineUI):
    """Placeholder UI for short-drama creation; to be implemented."""

    name = "short_drama"
    icon = "🎭"
    description = ""

    @property
    def display_name(self) -> str:
        return tr("pipeline.short_drama.name")

    def render(self, pixelle_video: Any) -> None:
        project_tab, character_tab, props_tab, scene_tab, storyboard_tab = st.tabs(
            [
                tr("pipeline.short_drama.sub.project"),
                tr("pipeline.short_drama.sub.character"),
                tr("pipeline.short_drama.sub.props"),
                tr("pipeline.short_drama.sub.scene"),
                tr("pipeline.short_drama.sub.storyboard"),
            ]
        )
        with project_tab:
            self._render_project_subpage(pixelle_video)
        with character_tab:
            self._render_character_subpage(pixelle_video)
        with props_tab:
            self._render_props_subpage(pixelle_video)
        with scene_tab:
            self._render_scene_subpage(pixelle_video)
        with storyboard_tab:
            self._render_storyboard_subpage(pixelle_video)

    def _render_project_subpage(self, _pixelle_video: Any) -> None:
        """项目：新建 / 加载（卡片网格）"""
        st.markdown(f"#### {tr('short_drama.project.section.new')}")
        self._render_new_project_form()
        st.divider()
        st.markdown(f"#### {tr('short_drama.project.section.load')}")
        if st.session_state.pop("short_drama_load_toast", None):
            st.toast(tr("short_drama.project.load_success"), icon="✅")
        projects = list_projects()
        self._render_active_project_banner()
        self._render_project_cards_grid(projects)

    def _render_new_project_form(self) -> None:
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
            st.error(_map_project_error(err_key))

    def _render_active_project_banner(self) -> None:
        work_path = get_work_path()
        if not work_path:
            st.caption(tr("short_drama.work.hint_select"))
            return
        name = get_work_name() or work_path
        st.info(tr("short_drama.work.current", name=name, path=work_path))

    def _render_project_cards_grid(self, projects: list[ProjectMeta]) -> None:
        if not projects:
            st.info(tr("short_drama.project.empty_list"))
            return
        n = _PROJECT_CARDS_PER_ROW
        for row_start in range(0, len(projects), n):
            cols = st.columns(n, gap="medium")
            for j in range(n):
                idx = row_start + j
                if idx >= len(projects):
                    continue
                proj = projects[idx]
                with cols[j]:
                    self._render_one_project_card(
                        proj, idx, is_active_project(proj.root_path)
                    )

    def _render_one_project_card(
        self, proj: ProjectMeta, card_index: int, is_active: bool
    ) -> None:
        h = _project_card_token(proj.root_path)
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

            path_short = _truncate_middle(
                proj.root_path, _PROJECT_CARD_PATH_DISPLAY_LEN
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
                    use_container_width=True,
                ):
                    if activate_project(proj.root_path):
                        st.session_state.short_drama_load_toast = True
                    st.rerun()
            with e_col:
                if st.button(
                    f"✏️ {tr('short_drama.project.edit')}",
                    key=f"sd_edit_{card_index}_{h}",
                    use_container_width=True,
                ):
                    _short_drama_project_edit_dialog(proj.root_path)
            with d_col:
                if st.button(
                    f"🗑️ {tr('short_drama.project.delete')}",
                    key=f"sd_del_{card_index}_{h}",
                    use_container_width=True,
                ):
                    _short_drama_project_delete_dialog(proj.root_path)

    def _render_work_path_gate(self) -> bool:
        """Return True if a project is loaded; otherwise show hint and return False."""
        if get_work_path():
            return True
        st.info(tr("short_drama.work.no_project"))
        return False

    def _render_character_subpage(self, _pixelle_video: Any) -> None:
        """角色 — 待实现"""
        if not self._render_work_path_gate():
            return
        st.caption(tr("short_drama.work.using_path", path=get_work_path()))

    def _render_props_subpage(self, _pixelle_video: Any) -> None:
        """道具 — 待实现"""
        if not self._render_work_path_gate():
            return
        st.caption(tr("short_drama.work.using_path", path=get_work_path()))

    def _render_scene_subpage(self, _pixelle_video: Any) -> None:
        """场景 — 待实现"""
        if not self._render_work_path_gate():
            return
        st.caption(tr("short_drama.work.using_path", path=get_work_path()))

    def _render_storyboard_subpage(self, _pixelle_video: Any) -> None:
        """分镜 — 待实现"""
        if not self._render_work_path_gate():
            return
        st.caption(tr("short_drama.work.using_path", path=get_work_path()))


register_pipeline_ui(ShortDramaPipelineUI)
