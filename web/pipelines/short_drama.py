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
Short Drama Pipeline — top-level entry & registration.

All feature implementations live under ``web/short_drama``; this module
only wires the pipeline into the registry and dispatches the five subpages
(项目 / 角色 / 道具 / 场景 / 分镜) to their dedicated render functions.
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from web.i18n import tr
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.short_drama.project_page import render_project_subpage
from web.short_drama.role_page import render_role_subpage
from web.short_drama.subpages import (
    render_props_subpage,
    render_scene_subpage,
    render_storyboard_subpage,
)

_SK_ACTIVE_SUBPAGE = "short_drama_active_subpage"


def _subpage_specs() -> dict[str, tuple[str, Callable[[Any], None]]]:
    return {
        "project": (
            tr("pipeline.short_drama.sub.project"),
            render_project_subpage,
        ),
        "character": (
            tr("pipeline.short_drama.sub.character"),
            render_role_subpage,
        ),
        "props": (
            tr("pipeline.short_drama.sub.props"),
            render_props_subpage,
        ),
        "scene": (
            tr("pipeline.short_drama.sub.scene"),
            render_scene_subpage,
        ),
        "storyboard": (
            tr("pipeline.short_drama.sub.storyboard"),
            render_storyboard_subpage,
        ),
    }


def _render_subpage_nav(specs: dict[str, tuple[str, Callable[[Any], None]]]) -> str:
    """Render short-drama subpage navigation without executing every subpage."""
    options = list(specs.keys())
    if st.session_state.get(_SK_ACTIVE_SUBPAGE) not in options:
        st.session_state[_SK_ACTIVE_SUBPAGE] = options[0]

    format_func = lambda key: specs[key][0]
    segmented_control = getattr(st, "segmented_control", None)
    if segmented_control is not None:
        active = segmented_control(
            tr("pipeline.short_drama.name"),
            options=options,
            format_func=format_func,
            key=_SK_ACTIVE_SUBPAGE,
            label_visibility="collapsed",
        )
    else:
        active = st.radio(
            tr("pipeline.short_drama.name"),
            options=options,
            format_func=format_func,
            key=_SK_ACTIVE_SUBPAGE,
            horizontal=True,
            label_visibility="collapsed",
        )
    return active or options[0]


class ShortDramaPipelineUI(PipelineUI):
    """Top-level UI for short-drama creation; dispatches to subpage modules."""

    name = "short_drama"
    icon = "🎭"
    description = ""

    @property
    def display_name(self) -> str:
        return tr("pipeline.short_drama.name")

    def render(self, pixelle_video: Any) -> None:
        specs = _subpage_specs()
        active = _render_subpage_nav(specs)
        specs[active][1](pixelle_video)


register_pipeline_ui(ShortDramaPipelineUI)
