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
Short Drama — ComfyUI image generation.

Dedicated ComfyKit execution path for the short-drama UI. Does not use
``pixelle_video.services.media.MediaService`` so role/prop/scene flows can
evolve independently (workflow params, progress hooks, result handling).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from loguru import logger

from web.short_drama import role_store

ProgressCallback = Callable[[int, str], None]


class ComfyImageGenerationError(Exception):
    """Raised when workflow validation or ComfyUI execution fails.

    ``code`` must be registered in ``web.short_drama.errors._ERR_I18N``.
    """

    def __init__(self, code: str, **fmt: str) -> None:
        self.code = code
        self.fmt = fmt
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedWorkflow:
    """Workflow file metadata used to invoke ComfyKit."""

    key: str
    path: Path
    source: str
    workflow_id: Optional[str] = None

    @property
    def comfy_input(self) -> str:
        """Value passed as the first argument to ``ComfyKit.execute``."""
        if self.source == "runninghub" and self.workflow_id:
            return self.workflow_id
        return str(self.path.resolve())


def workflow_path_for_key(workflow_key: str) -> Path:
    return Path("workflows") / workflow_key


def validate_workflow(workflow_key: str) -> tuple[bool, str, dict[str, str]]:
    """Validate workflow JSON before generation.

    Returns:
        (ok, error_key, format_kwargs) — ``error_key`` is empty when ``ok``.
    """
    if not workflow_key:
        return False, "workflow_missing", {"path": "?"}

    workflow_path = workflow_path_for_key(workflow_key)
    is_selfhost = workflow_key.startswith("selfhost/")

    if not workflow_path.is_file():
        err_key = (
            "workflow_missing_selfhost" if is_selfhost else "workflow_missing"
        )
        return False, err_key, {"path": str(workflow_path)}

    try:
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "workflow_unreadable", {"path": str(workflow_path)}

    if isinstance(data, dict) and data.get("source") == "runninghub":
        wf_id = str(data.get("workflow_id") or "").strip()
        if not wf_id:
            return False, "workflow_id_missing", {"path": str(workflow_path)}

    return True, "", {}


def resolve_workflow(workflow_key: str) -> ResolvedWorkflow:
    """Load workflow metadata; raises ``ComfyImageGenerationError`` on failure."""
    ok, err_key, fmt = validate_workflow(workflow_key)
    if not ok:
        raise ComfyImageGenerationError(err_key, **fmt)

    workflow_path = workflow_path_for_key(workflow_key)
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    source = "selfhost"
    workflow_id: Optional[str] = None
    if isinstance(data, dict) and data.get("source") == "runninghub":
        source = "runninghub"
        workflow_id = str(data.get("workflow_id") or "").strip() or None

    return ResolvedWorkflow(
        key=workflow_key,
        path=workflow_path,
        source=source,
        workflow_id=workflow_id,
    )


def build_workflow_params(
    *,
    prompt: str,
    ref_image_path: Optional[str] = None,
    ref_image_param: str = "image",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"prompt": prompt}
    if ref_image_path:
        params[ref_image_param] = ref_image_path
    if extra:
        params.update(extra)
    return params


async def ensure_local_image_in_project_temp(image_ref: str) -> str:
    """Download or copy ``image_ref`` into ``<project>/temp/`` and return path."""
    if image_ref.startswith(("http://", "https://")):
        timeout = httpx.Timeout(300.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(image_ref)
            resp.raise_for_status()
            data = resp.content
        ext = Path(image_ref.split("?", 1)[0]).suffix.lower()
        local = role_store.save_bytes_to_temp(
            data=data,
            prefer_ext=ext if ext in {".png", ".jpg", ".webp"} else None,
        )
        if local is None:
            raise ComfyImageGenerationError("temp_write_failed")
        return local

    src = Path(image_ref)
    if not src.is_file():
        raise ComfyImageGenerationError("generated_image_missing")

    try:
        data = src.read_bytes()
    except OSError as exc:
        raise ComfyImageGenerationError("generated_image_unreadable") from exc

    local = role_store.save_bytes_to_temp(
        data=data,
        prefer_ext=src.suffix.lower() or None,
    )
    if local is None:
        return str(src.resolve())
    return local


async def execute_comfy_image_workflow(
    *,
    pixelle_video: Any,
    workflow_key: str,
    prompt: str,
    ref_image_path: Optional[str] = None,
    ref_image_param: str = "image",
    extra_params: Optional[dict[str, Any]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> str:
    """Run an image workflow via ComfyKit and return a path under project ``temp/``."""
    def _progress(value: int, text: str) -> None:
        if on_progress is not None:
            on_progress(value, text)

    workflow = resolve_workflow(workflow_key)
    workflow_params = build_workflow_params(
        prompt=prompt,
        ref_image_path=ref_image_path,
        ref_image_param=ref_image_param,
        extra=extra_params,
    )

    _progress(10, "executing")
    kit = await pixelle_video._get_or_create_comfykit()
    logger.info(
        "Short drama image workflow: key={} source={} input={}",
        workflow.key,
        workflow.source,
        workflow.comfy_input,
    )
    logger.debug("Workflow parameters: {}", workflow_params)

    result = await kit.execute(workflow.comfy_input, workflow_params)

    if result.status != "completed":
        detail = (result.msg or "").strip()
        logger.error("ComfyUI image generation failed: {}", detail or "(no message)")
        if detail:
            raise ComfyImageGenerationError("generation_failed", error=detail)
        raise ComfyImageGenerationError("workflow_failed")

    if not result.images:
        logger.error("Workflow completed but returned no images")
        raise ComfyImageGenerationError("no_image_output")

    image_url = result.images[0]
    logger.info("ComfyUI image generated: {}", image_url)

    _progress(70, "downloading")
    local_path = await ensure_local_image_in_project_temp(image_url)
    _progress(95, "saving")
    return local_path
