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
Short Drama — ComfyUI workflow service (image / video / audio / …).

Workflow JSON under ``web/short_drama/workflow/`` must be ComfyUI **API format**:
``{ "<node_id>": { "class_type": "...", "inputs": { ... } }, ... } }``.

Functions return ``(value, err, fmt)``; ``err`` empty on success (see ``role_store``).
Callers patch ``workflow`` inputs in business code, then :func:`execute_comfy_workflow`.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from comfyui_xy import AsyncComfyUiClient, ComfyResponse, ComfyUiError
from loguru import logger

from web.short_drama import role_store

ProgressCallback = Callable[[int, str], None]
ErrFmt = dict[str, str]

_WORKFLOW_DIR = Path(__file__).resolve().parent / "workflow"
_DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
_EXECUTION_TIMEOUT_SEC = 600


@dataclass
class ComfyWorkflowResult:
    paths: list[str] = field(default_factory=list)


def short_drama_workflow_dir() -> Path:
    _WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    return _WORKFLOW_DIR


def workflow_display_path(workflow_key: str) -> str:
    return f"web/short_drama/workflow/{workflow_key}"


def _sanitize_workflow_key(workflow_key: str) -> str:
    key = (workflow_key or "").strip().replace("\\", "/").lstrip("/")
    if not key or ".." in Path(key).parts:
        return ""
    return key


def _is_valid_workflow(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    return any(isinstance(n, dict) and "class_type" in n for n in data.values())


def load_workflow(
    workflow_key: str,
) -> tuple[Optional[dict[str, Any]], str, ErrFmt]:
    """Load workflow JSON; on success ``err`` is empty."""
    key = _sanitize_workflow_key(workflow_key)
    display = workflow_display_path(key or (workflow_key or "?"))
    if not key:
        return None, "workflow_key_invalid", {"path": display}

    path = short_drama_workflow_dir() / key
    if not path.is_file():
        return None, "workflow_missing", {"path": display}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, "workflow_unreadable", {"path": display}

    if not _is_valid_workflow(data):
        return None, "workflow_invalid", {"path": display}
    return copy.deepcopy(data), "", {}


def comfyui_url_from_pixelle(pixelle_video: Any) -> str:
    config = getattr(pixelle_video, "config", None) or {}
    comfyui = config.get("comfyui") if isinstance(config, dict) else {}
    url = str((comfyui or {}).get("comfyui_url") or "").strip()
    return url or _DEFAULT_COMFYUI_URL


async def upload_image_to_comfy(
    pixelle_video: Any,
    image_path: str,
) -> tuple[Optional[str], str, ErrFmt]:
    """Upload one local image file to ComfyUI; returns input filename on success."""
    client = AsyncComfyUiClient(
        url=comfyui_url_from_pixelle(pixelle_video),
        raise_on_error=True,
        execution_timeout=_EXECUTION_TIMEOUT_SEC,
    )
    try:
        filename = await client.upload_image(image_path)
        if not filename:
            return None, "ref_upload_failed", {}
        return filename, "", {}
    finally:
        await client.close()


def _save_responses(
    responses: list[ComfyResponse],
) -> tuple[Optional[list[str]], str, ErrFmt]:
    paths: list[str] = []
    for response in responses:
        ext = Path(response.filename or "").suffix.lower()
        if not ext and response.file_type == "image":
            ext = ".png"
        local = role_store.save_bytes_to_temp(data=response.data, prefer_ext=ext or None)
        if local is None:
            return None, "temp_write_failed", {}
        paths.append(local)
    return paths, "", {}


async def execute_comfy_workflow(
    *,
    pixelle_video: Any,
    workflow: dict[str, Any],
    on_progress: Optional[ProgressCallback] = None,
) -> tuple[Optional[ComfyWorkflowResult], str, ErrFmt]:
    """Submit a prepared API workflow graph to ComfyUI and save file outputs to project ``temp/``."""
    def _progress(value: int, text: str) -> None:
        if on_progress:
            on_progress(value, text)

    comfy_url = comfyui_url_from_pixelle(pixelle_video)
    logger.info("ComfyUI workflow: url={} nodes={}", comfy_url, len(workflow))

    client = AsyncComfyUiClient(
        url=comfy_url,
        raise_on_error=True,
        execution_timeout=_EXECUTION_TIMEOUT_SEC,
    )
    try:
        _progress(10, "executing")
        try:
            results = await client.process_workflow(workflow)
        except ComfyUiError as exc:
            return None, "execution_failed", {"error": str(exc)}
    finally:
        await client.close()

    files = [r for r in results if r.is_file and r.data]
    if not files:
        return None, "no_output", {"kind": "file"}

    _progress(70, "saving")
    paths, err, fmt = _save_responses(files)
    if err:
        return None, err, fmt

    _progress(95, "saving")
    return ComfyWorkflowResult(paths=paths or []), "", {}
