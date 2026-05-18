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
Short Drama — preset prompt templates for image generation.

Shared by all subpages (角色 / 道具 / 场景 / 分镜, …). Each template has:
    id: Stable key for Streamlit widget keys.
    label: Button text shown above the prompt textarea.
    text: Content injected into the prompt field on click (user may edit after).

Edit or append entries in :data:`PROMPT_TEMPLATES` freely.

:data:`GENERATION_PROMPT_SUFFIX` appends extra instructions when generating
特写 / 三视图 (see ``role_page``).
"""

from __future__ import annotations

from typing import Literal

GenerationKind = Literal["closeup", "three_view"]

# Appended to the user prompt when generating specific asset types.
GENERATION_PROMPT_SUFFIX: dict[GenerationKind, str] = {
    "closeup": (
        "角色面部与肩部特写，正面构图，五官清晰，背景简洁，高清细节。"
    ),
    "three_view": (
        "角色三视图设定图：正面、左侧面、背面并排展示，全身比例一致，"
        "白底或浅灰底，线条干净，便于建模参考。"
    ),
}

# TODO: 自由修改/扩展提示词预置模板（label 会显示在按钮上，text 会注入到提示词框）。
PROMPT_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "realistic_to_drawing",
        "label": "真人转绘",
        "text": (
            "将参考图中的真人转绘为统一的二次元/插画风角色立绘：\n"
            "- 五官与发型保持高度一致，体态自然，正面视角；\n"
            "- 色彩明亮、线条干净，背景使用纯色或浅色渐变；\n"
            "- 输出 1:1 比例，4K 清晰度。"
        ),
    },
]
