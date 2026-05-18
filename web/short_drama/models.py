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
Short Drama — generation models (ComfyUI workflow mapping).

Shared by all subpages (角色 / 道具 / 场景 / 分镜, …). ``MODEL_REGISTRY`` is keyed by
media category (``image`` / ``video``); each value maps a model id to workflow
metadata for ``web.short_drama.comfy_image`` / ComfyKit.

Fields per model:
    label: Display name in the model selectbox.
    workflow_key: Path under ``workflows/`` (e.g. ``selfhost/foo.json``).
    requires_ref_image: If True, generation fails without a reference upload.
    ref_image_param: Workflow parameter name for the reference image path.
"""

from __future__ import annotations

from typing import Any

# TODO: 把你导出的 Qwen-Image-Edit-2511 ComfyUI 工作流 JSON（API 格式）放到
# ``workflows/selfhost/image_qwen_edit_2511.json``；如需更换文件名，同时更新这里的
# ``workflow_key``。工作流内对应的"参考图"节点入参名要与 ``ref_image_param`` 一致。
MODEL_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {
    "image": {
        "Qwen-Image-Edit-2511": {
            "label": "Qwen-Image-Edit-2511",
            "workflow_key": "selfhost/image_qwen_edit_2511.json",
            "requires_ref_image": False,
            "ref_image_param": "image",
        },
    },
    "video": {},
}

IMAGE_MODEL_REGISTRY: dict[str, dict[str, Any]] = MODEL_REGISTRY["image"]
VIDEO_MODEL_REGISTRY: dict[str, dict[str, Any]] = MODEL_REGISTRY["video"]
