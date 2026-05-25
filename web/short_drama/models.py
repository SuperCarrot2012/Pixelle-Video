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
metadata for ``web.short_drama.comfy_service`` / local ComfyUI (``web/short_drama/workflow/``).

Fields per model:
    label: Display name in the model selectbox.
    workflow_key: Maps subpage scene → workflow JSON filename under ``web/short_drama/workflow/``.
        Keys: ``role`` | ``props`` | ``scene`` | ``storyboard`` (see :data:`WORKFLOW_SCENES`).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

WorkflowScene = Literal["role", "props", "scene", "storyboard"]

WORKFLOW_SCENES: tuple[WorkflowScene, ...] = (
    "role",
    "props",
    "scene",
    "storyboard",
)

# TODO: 把你导出的 Qwen-Image-Edit-2511 ComfyUI 工作流 JSON（API 格式）放到
# ``web/short_drama/workflow/`` 下对应文件；各子页场景可配置不同 JSON。
# 参考图在业务页调用 ``comfy_service.upload_image_to_comfy``（每张图一次）并写入 LoadImage 节点。
MODEL_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {
    "image": {
        "Qwen-Image-Edit-2511": {
            "label": "Qwen-Image-Edit-2511",
            "workflow_key": {
                "role": "qwen-image-edit-2511-roles.json",
                "props": "qwen-image-edit-2511-roles.json",
                "scene": "qwen-image-edit-2511-roles.json",
                "storyboard": "qwen-image-edit-2511-roles.json",
            },
        },
    },
    "video": {},
}

IMAGE_MODEL_REGISTRY: dict[str, dict[str, Any]] = MODEL_REGISTRY["image"]
VIDEO_MODEL_REGISTRY: dict[str, dict[str, Any]] = MODEL_REGISTRY["video"]


def get_workflow_key_for_scene(
    model_info: dict[str, Any],
    scene: WorkflowScene,
) -> Optional[str]:
    """Return workflow filename for ``scene``, or ``None`` if not configured."""
    mapping = model_info.get("workflow_key")
    if not isinstance(mapping, dict):
        return None
    key = mapping.get(scene)
    if not isinstance(key, str) or not key.strip():
        return None
    return key.strip()
