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
only wires the pipeline into the registry and dispatches the five sub-tabs
(项目 / 角色 / 道具 / 场景 / 分镜) to their dedicated render functions.
"""

from __future__ import annotations

from typing import Any

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


class ShortDramaPipelineUI(PipelineUI):
    """Top-level UI for short-drama creation; dispatches to subpage modules."""

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
            render_project_subpage(pixelle_video)
        with character_tab:
            render_role_subpage(pixelle_video)
        with props_tab:
            render_props_subpage(pixelle_video)
        with scene_tab:
            render_scene_subpage(pixelle_video)
        with storyboard_tab:
            render_storyboard_subpage(pixelle_video)


register_pipeline_ui(ShortDramaPipelineUI)
