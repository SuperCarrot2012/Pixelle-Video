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
        "人像特写，正对镜头，从头顶到锁骨完整展示，不裁切头顶，head to collarbone complete，\n"
        "素灰纯色背景，均匀柔光，无硬阴影。"
    ),
    "three_view": (
        "角色三视图设定图。\n"
        "character design sheet, character turnaround,\n"
        "同一画面左至右并排：正视图+侧视图+背视图。\n"
        "全身立像从头顶到脚底完整展示，full body head to toe，不裁切头顶和脚部，\n"
        "自然站立，素灰纯色背景，均匀柔光，无硬阴影，\n"
        "三视图一致性，高精度建模清晰，\n"
        "头与身体的比例为1：8，腰部以上占身体65%，身材修长，大长腿。"
    ),
}

# TODO: 自由修改/扩展提示词预置模板（label 会显示在按钮上，text 会注入到提示词框）。
PROMPT_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "realistic_to_drawing",
        "label": "真人转绘",
        "text": (
            "将参考图中的角色，转绘成真人角色设定图。把皮肤材质转换为真实人类皮肤质感。"
            "转为影棚商业人像摄影光效，电影级光影，真人质感，柔光箱主光，纯色浅灰背景，超高分辨率，高清人像。"
        ),
    },
]
