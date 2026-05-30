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
Short Drama — 角色 (Roles) subpage.

Layout:
- Top   : existing role cards.
- Below : two columns — left edit form (cn/en name, description, prompt, …),
          right preview panel for generated images.

Implementation notes:
- Generated/uploaded images are cached under ``<project>/temp/`` using a
  content hash as filename (see role_store.save_bytes_to_temp).
- Model → workflow mapping: ``web.short_drama.models.IMAGE_MODEL_REGISTRY``.
- Preset prompts: ``web.short_drama.prompt_templates.PROMPT_TEMPLATES``.
- ComfyUI execution: ``web.short_drama.comfy_service`` (``comfyui_xy``, not ComfyKit).
"""

from __future__ import annotations

import base64
import random
import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from loguru import logger
from PIL import Image, ImageOps

from web.i18n import tr
from web.short_drama import role_store
from web.short_drama.comfy_service import (
    execute_comfy_workflow,
    load_workflow,
    upload_image_to_comfy,
)
from web.short_drama.dialogs import (
    role_delete_dialog,
)
from web.short_drama.errors import map_error
from web.short_drama.media_server import _MEDIA_PREFIX, register_media_file
from web.short_drama.models import IMAGE_MODEL_REGISTRY, get_workflow_key_for_scene
from web.short_drama.prompt_templates import (
    GENERATION_PROMPT_SUFFIX,
    PROMPT_TEMPLATES,
    GenerationKind,
)
from web.short_drama.role_store import RoleMeta
from web.short_drama.work_context import get_work_path
from web.utils.async_helpers import run_async

# ---------------------------------------------------------------------------
# Session-state keys
# ---------------------------------------------------------------------------

_SK_PROMPT = "sd_role_prompt"
_SK_CN_NAME = "sd_role_cn_name"
_SK_EN_NAME = "sd_role_en_name"
_SK_DESC = "sd_role_desc"
_SK_MODEL = "sd_role_model"
_SK_PREVIEWS = "sd_role_previews"  # list[dict]
_SK_LAST_ERROR = "sd_role_last_error"
_SK_LAST_SUCCESS = "sd_role_last_success"
_SK_EDIT_ERROR = "sd_role_edit_error"
_SK_EDIT_SUCCESS = "sd_role_edit_success"
_SK_EDITING_ROLE = "sd_role_editing_en"  # english_name when editing existing role
_SK_RESET_PENDING = "sd_role_reset_pending"
_SK_GEN_PENDING = "sd_role_gen_pending"  # GenerationKind while awaiting ComfyUI

_MAX_REF_IMAGES = 3

# qwen-image-edit-2511-roles.json: LoadImage 8/9/10 → TextEncode node 11 image1/image2/image3
_QWEN_ROLE_REF_SLOTS: tuple[tuple[str, str], ...] = (
    ("8", "image1"),
    ("9", "image2"),
    ("10", "image3"),
)

# qwen-image-edit-2511-roles.json — 生成前动态覆盖（按需修改）
_QWEN_ROLE_KSAMPLER_NODE_ID = "13"
_QWEN_ROLE_EMPTY_LATENT_NODE_ID = "16"
# EmptyLatentImage: (width, height, batch_size) per generation kind (model-agnostic)
_ROLE_LATENT_BY_KIND: dict[GenerationKind, tuple[int, int, int]] = {
    "closeup": (1440, 2560, 4),
    "three_view": (3240, 2560, 4),
}
# Preview thumbnail size (px); aspect ratio matches ``_ROLE_LATENT_BY_KIND``, fixed per kind.
_ROLE_PREVIEW_THUMB_BY_KIND: dict[GenerationKind, tuple[int, int]] = {
    "closeup": (270, 480),
    "three_view": (540, 427),
}
_PREVIEW_THUMB_GAP_PX = 12
# Edit form (left) vs preview panel (right) width ratio; e.g. [2, 3] ≈ 40% / 60%.
_ROLE_EDIT_PREVIEW_COLUMNS: tuple[int, ...] = (2, 3)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def render_role_subpage(pixelle_video: Any) -> None:
    """Render the 角色 subpage; gated by the active project."""
    if not get_work_path():
        st.info(tr("short_drama.work.no_project"))
        return

    role_store.ensure_dirs()

    st.caption(tr("short_drama.work.using_path", path=get_work_path()))

    _consume_toasts()

    _render_existing_roles()

    st.divider()

    gen_pending = st.session_state.get(_SK_GEN_PENDING)
    left, right = st.columns(list(_ROLE_EDIT_PREVIEW_COLUMNS), gap="medium")
    with left:
        _render_edit_form(pixelle_video)
    with right:
        _render_preview_panel(disabled=bool(gen_pending))

    # Run after both columns render so the preview stays disabled during ComfyUI wait.
    if gen_pending:
        kind = st.session_state.pop(_SK_GEN_PENDING)
        ref_files = _limit_ref_images(st.session_state.get("sd_role_ref_image"))
        with left:
            _execute_image_generation(pixelle_video, ref_files, kind)


# ---------------------------------------------------------------------------
# Toasts (cross-rerun feedback)
# ---------------------------------------------------------------------------


def _consume_toasts() -> None:
    """Page-level feedback (e.g. delete role, promote preview)."""
    err = st.session_state.pop(_SK_LAST_ERROR, None)
    if err:
        st.error(err)
    ok = st.session_state.pop(_SK_LAST_SUCCESS, None)
    if ok:
        st.toast(ok, icon="✅")


def _set_edit_error(message: str) -> None:
    st.session_state[_SK_EDIT_ERROR] = message


def _set_edit_success(message: str) -> None:
    st.session_state[_SK_EDIT_SUCCESS] = message


def _consume_edit_feedback() -> None:
    """Feedback scoped to the edit-role form (save / generate actions)."""
    err = st.session_state.pop(_SK_EDIT_ERROR, None)
    if err:
        st.error(err)
    ok = st.session_state.pop(_SK_EDIT_SUCCESS, None)
    if ok:
        st.success(ok)


# ---------------------------------------------------------------------------
# Left column — edit form
# ---------------------------------------------------------------------------


def _load_role_into_edit_form(meta: RoleMeta) -> None:
    """Fill the edit-area widgets from an existing role record."""
    st.session_state[_SK_CN_NAME] = meta.chinese_name
    st.session_state[_SK_EN_NAME] = meta.english_name
    st.session_state[_SK_DESC] = meta.description
    if meta.prompt:
        st.session_state[_SK_PROMPT] = meta.prompt
    if meta.model and meta.model in IMAGE_MODEL_REGISTRY:
        st.session_state[_SK_MODEL] = meta.model
    st.session_state[_SK_EDITING_ROLE] = meta.english_name


def _editing_english_name() -> str:
    return (st.session_state.get(_SK_EDITING_ROLE) or "").strip()


def _reset_edit_form() -> None:
    """Clear all edit-area fields and exit in-place editing mode.

    Must run before any keyed widgets in ``_render_edit_form`` are drawn.
    """
    st.session_state.pop(_SK_EDITING_ROLE, None)
    st.session_state[_SK_CN_NAME] = ""
    st.session_state[_SK_EN_NAME] = ""
    st.session_state[_SK_DESC] = ""
    st.session_state[_SK_PROMPT] = ""
    st.session_state.pop("sd_role_ref_image", None)
    st.session_state.pop("sd_role_model_select", None)
    st.session_state[_SK_MODEL] = next(iter(IMAGE_MODEL_REGISTRY))
    st.session_state.pop(_SK_EDIT_ERROR, None)
    st.session_state.pop(_SK_EDIT_SUCCESS, None)


def _apply_pending_edit_form_reset() -> None:
    if not st.session_state.pop(_SK_RESET_PENDING, False):
        return
    _reset_edit_form()


def _render_edit_form(pixelle_video: Any) -> None:
    _apply_pending_edit_form_reset()

    st.markdown(f"#### {tr('short_drama.role.section.edit')}")
    editing_en = _editing_english_name()
    if editing_en:
        st.caption(tr("short_drama.role.editing_hint", en=editing_en))

    # NOTE: we intentionally use ``st.container`` instead of ``st.form`` so the
    # prompt-template buttons (which need to immediately mutate the prompt
    # textarea on click) can live in the same visual container as the rest of
    # the inputs. With ``st.form``, inner buttons would only fire on submit.
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input(
                tr("short_drama.role.cn_name"),
                key=_SK_CN_NAME,
                placeholder=tr("short_drama.role.cn_name_placeholder"),
            )
        with c2:
            st.text_input(
                tr("short_drama.role.en_name"),
                key=_SK_EN_NAME,
                placeholder=tr("short_drama.role.en_name_placeholder"),
                help=(
                    tr("short_drama.role.en_name_edit_help")
                    if editing_en
                    else tr("short_drama.role.en_name_help")
                ),
                disabled=bool(editing_en),
            )

        st.text_area(
            tr("short_drama.role.description"),
            key=_SK_DESC,
            height=100,
            placeholder=tr("short_drama.role.description_placeholder"),
        )

        # Template buttons sit right above the prompt textarea so the
        # relationship between them is visually obvious.
        _render_prompt_template_buttons()

        st.text_area(
            tr("short_drama.role.prompt"),
            key=_SK_PROMPT,
            height=400,
            placeholder=tr("short_drama.role.prompt_placeholder"),
            help=tr("short_drama.role.prompt_help"),
        )

        ref_image = st.file_uploader(
            tr("short_drama.role.ref_image"),
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            help=tr("short_drama.role.ref_image_help", max=_MAX_REF_IMAGES),
            key="sd_role_ref_image",
        )
        ref_files = _limit_ref_images(ref_image)

        model_labels = [info["label"] for info in IMAGE_MODEL_REGISTRY.values()]
        model_keys = list(IMAGE_MODEL_REGISTRY.keys())
        default_index = 0
        if _SK_MODEL in st.session_state and st.session_state[_SK_MODEL] in model_keys:
            default_index = model_keys.index(st.session_state[_SK_MODEL])
        chosen_label = st.selectbox(
            tr("short_drama.role.model"),
            options=model_labels,
            index=default_index,
            help=tr("short_drama.role.model_help"),
            key="sd_role_model_select",
        )
        st.session_state[_SK_MODEL] = model_keys[model_labels.index(chosen_label)]

        btn_profile, btn_closeup, btn_three, btn_reset = st.columns(4)
        with btn_profile:
            if st.button(
                tr("short_drama.role.save_profile"),
                key="sd_role_save_profile_btn",
                width="stretch",
            ):
                _handle_save_profile()
        with btn_closeup:
            if st.button(
                tr("short_drama.role.generate_closeup"),
                key="sd_role_generate_closeup_btn",
                width="stretch",
            ):
                _queue_image_generation("closeup")
        with btn_three:
            if st.button(
                tr("short_drama.role.generate_three_view"),
                key="sd_role_generate_three_view_btn",
                width="stretch",
            ):
                _queue_image_generation("three_view")
        with btn_reset:
            if st.button(
                tr("short_drama.role.reset_form"),
                key="sd_role_reset_form_btn",
                width="stretch",
            ):
                st.session_state[_SK_RESET_PENDING] = True
                st.rerun()

        _consume_edit_feedback()


def _render_prompt_template_buttons() -> None:
    """Render preset prompt-template buttons just above the prompt textarea."""
    st.caption(tr("short_drama.role.prompt_templates"))
    with st.container(horizontal=True, gap="small", vertical_alignment="top"):
        for tmpl in PROMPT_TEMPLATES:
            if st.button(
                tmpl["label"],
                key=f"sd_role_tmpl_{tmpl['id']}",
                width="content",
            ):
                st.session_state[_SK_PROMPT] = tmpl["text"]
                st.rerun()


# ---------------------------------------------------------------------------
# Right column — preview panel
# ---------------------------------------------------------------------------

def _preview_thumb_size(kind: str) -> tuple[int, int]:
    if kind == "three_view":
        return _ROLE_PREVIEW_THUMB_BY_KIND["three_view"]
    return _ROLE_PREVIEW_THUMB_BY_KIND["closeup"]


def _preview_image_paths(item: dict) -> list[str]:
    """Paths for one generation batch (supports legacy single ``image_path``)."""
    paths = item.get("image_paths")
    if isinstance(paths, list) and paths:
        return [str(p) for p in paths if p]
    legacy = item.get("image_path")
    if legacy:
        return [str(legacy)]
    return []


def _preview_thumb_paths(item: dict) -> list[str]:
    """Thumbnail paths for display; falls back to originals for legacy previews."""
    thumbs = item.get("thumb_paths")
    if isinstance(thumbs, list) and thumbs:
        return [str(p) for p in thumbs if p]
    return _preview_image_paths(item)


def _preview_selected_index(item: dict, path_count: int) -> int:
    if path_count <= 0:
        return -1
    raw = item.get("selected_image_index", 0)
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        idx = 0
    if idx < 0 or idx >= path_count:
        return 0
    return idx


def _set_preview_selected(preview_idx: int, image_idx: int) -> None:
    previews = list(st.session_state.get(_SK_PREVIEWS, []))
    if 0 <= preview_idx < len(previews):
        paths = _preview_image_paths(previews[preview_idx])
        if 0 <= image_idx < len(paths):
            previews[preview_idx]["selected_image_index"] = image_idx
            st.session_state[_SK_PREVIEWS] = previews


def _thumbnail_path_for(image_path: str, width: int, height: int) -> Path:
    path = Path(image_path)
    return path.with_name(f"{path.stem}.thumb_{width}x{height}.jpg")


def _ensure_preview_thumbnail(image_path: str, width: int, height: int) -> str:
    """Create a lightweight fixed-size thumbnail for the preview grid."""
    path = Path(image_path)
    if not path.is_file():
        return image_path

    thumb = _thumbnail_path_for(image_path, width, height)
    if thumb.is_file():
        return str(thumb.resolve())

    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((width, height), Image.Resampling.LANCZOS)

            canvas = Image.new("RGB", (width, height), (255, 255, 255))
            left = (width - im.width) // 2
            top = (height - im.height) // 2
            canvas.paste(im, (left, top))
            canvas.save(thumb, "JPEG", quality=88, optimize=True)
    except OSError:
        logger.exception("Failed to create preview thumbnail: {}", image_path)
        return image_path

    return str(thumb.resolve())


@st.cache_data(show_spinner=False)
def _preview_thumb_data_uri(thumb_path: str) -> str:
    path = Path(thumb_path)
    if not path.is_file():
        return ""
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _preview_image_url(image_path: str) -> str:
    token, port = register_media_file(image_path)
    return f"http://127.0.0.1:{port}/{_MEDIA_PREFIX}{token}"


def _lightbox_dom_id(preview_idx: int, image_idx: int) -> str:
    return f"sd-role-lightbox-{preview_idx}-{image_idx}"


def _render_preview_thumb_cell(
    thumb_path: str,
    *,
    image_url: str,
    lightbox_id: str,
    thumb_width: int,
    thumb_height: int,
    selected: bool,
) -> None:
    """Render one fixed-size thumbnail with no grey letterbox background."""
    data_uri = _preview_thumb_data_uri(thumb_path)
    if not data_uri:
        st.warning(tr("short_drama.role.err.preview_missing"))
        return
    border = "2px solid #ff4b4b" if selected else "1px solid rgba(128,128,128,0.35)"
    st.markdown(
        (
            f'<a href="#{lightbox_id}" style="display:block;width:{thumb_width}px;'
            'line-height:0;text-decoration:none;">'
            f'<img src="{data_uri}" alt="" '
            f'style="width:{thumb_width}px;height:{thumb_height}px;'
            f'object-fit:contain;display:block;border:{border};'
            'border-radius:4px;box-sizing:border-box;" />'
            '</a>'
            f'<a id="{lightbox_id}" class="sd-role-lightbox" href="#">'
            f'<img src="{image_url}" alt="" />'
            '</a>'
        ),
        unsafe_allow_html=True,
    )


def _render_preview_tile(
    *,
    preview_idx: int,
    image_idx: int,
    image_path: str,
    thumb_path: str,
    thumb_width: int,
    thumb_height: int,
    selected: bool,
    disabled: bool,
) -> None:
    """One fixed-width preview tile: clickable image + centered select button."""
    image_url = _preview_image_url(image_path)
    lightbox_id = _lightbox_dom_id(preview_idx, image_idx)
    with st.container(width=thumb_width):
        _render_preview_thumb_cell(
            thumb_path,
            image_url=image_url,
            lightbox_id=lightbox_id,
            thumb_width=thumb_width,
            thumb_height=thumb_height,
            selected=selected,
        )
        _, c_select, _ = st.columns([1, 2, 1], gap="small")
        with c_select:
            if st.button(
                tr("short_drama.role.preview_select"),
                key=f"sd_role_sel_{preview_idx}_{image_idx}",
                width="stretch",
                disabled=disabled,
            ):
                _set_preview_selected(preview_idx, image_idx)
                st.rerun()


def _render_preview_batch_card(
    item: dict,
    preview_idx: int,
    *,
    disabled: bool,
) -> None:
    """One preview cell: fixed-size thumbnails auto-wrap, each with two actions."""
    paths = _preview_image_paths(item)
    if not paths:
        st.warning(tr("short_drama.role.err.preview_missing"))
        return

    kind = item.get("generation_kind") or "closeup"
    thumb_w, thumb_h = _preview_thumb_size(kind)
    thumb_paths = _preview_thumb_paths(item)
    if len(thumb_paths) != len(paths):
        thumb_paths = paths
    thumb_paths = [
        _ensure_preview_thumbnail(path, thumb_w, thumb_h)
        if thumb_path == path
        else thumb_path
        for path, thumb_path in zip(paths, thumb_paths)
    ]
    selected_idx = _preview_selected_index(item, len(paths))

    caption = tr(
        "short_drama.role.preview_caption",
        cn=item.get("chinese_name") or "-",
        en=item.get("english_name") or "-",
        model=item.get("model") or "-",
        kind=_generation_kind_label(kind),
        count=len(paths),
    )
    st.caption(caption)
    flow_cls = f"sd-role-preview-flow-{preview_idx}"
    st.markdown(
        f"""
        <div class="{flow_cls}"></div>
        <style>
        .sd-role-lightbox {{
            position: fixed;
            inset: 0;
            z-index: 999999;
            display: none;
            align-items: center;
            justify-content: center;
            background: rgba(0, 0, 0, 0.86);
            cursor: zoom-out;
            padding: 2vh 2vw;
            box-sizing: border-box;
        }}
        .sd-role-lightbox:target {{
            display: flex;
        }}
        .sd-role-lightbox img {{
            max-width: 96vw;
            max-height: 96vh;
            width: auto;
            height: auto;
            object-fit: contain;
            box-shadow: 0 0 24px rgba(0, 0, 0, 0.6);
        }}
        div.{flow_cls} + div[data-testid="stHorizontalBlock"] {{
            flex-wrap: wrap !important;
            gap: {_PREVIEW_THUMB_GAP_PX}px !important;
            align-items: flex-start !important;
        }}
        div.{flow_cls} + div[data-testid="stHorizontalBlock"] > div {{
            flex: 0 0 auto !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(horizontal=True, gap="small", vertical_alignment="top"):
        for image_idx, image_path in enumerate(paths):
            thumb_path = thumb_paths[image_idx]
            _render_preview_tile(
                preview_idx=preview_idx,
                image_idx=image_idx,
                image_path=image_path,
                thumb_path=thumb_path,
                thumb_width=thumb_w,
                thumb_height=thumb_h,
                selected=(image_idx == selected_idx),
                disabled=disabled,
            )

    if selected_idx >= 0:
        st.caption(
            tr("short_drama.role.preview_selected_hint", index=selected_idx + 1)
        )

    selected_path = paths[selected_idx] if selected_idx >= 0 else ""
    a, b = st.columns([3, 1])
    with a:
        st.caption(
            tr("short_drama.role.preview_source", path=selected_path or "-")
        )
    with b:
        if st.button(
            tr("short_drama.role.preview_promote"),
            key=f"sd_role_promote_{preview_idx}",
            type="primary",
            width="stretch",
            disabled=disabled or selected_idx < 0,
        ):
            _promote_preview_to_official(preview_idx)


def _render_preview_panel(*, disabled: bool = False) -> None:
    st.markdown(f"#### {tr('short_drama.role.section.preview')}")
    with st.container(border=True):
        previews: list[dict] = st.session_state.get(_SK_PREVIEWS, [])
        if not previews:
            st.info(tr("short_drama.role.preview_empty"))
            # Reserve some visual space even when empty.
            st.markdown("&nbsp;\n\n&nbsp;\n\n&nbsp;", unsafe_allow_html=True)
            return

        if st.button(
            tr("short_drama.role.preview_clear"),
            key="sd_role_preview_clear",
            disabled=disabled,
        ):
            st.session_state[_SK_PREVIEWS] = []
            st.rerun()

        # Newest first.
        for i, item in enumerate(reversed(previews)):
            idx = len(previews) - 1 - i
            _render_preview_batch_card(item, idx, disabled=disabled)
            st.divider()


# ---------------------------------------------------------------------------
# Existing roles list
# ---------------------------------------------------------------------------


def _render_existing_roles() -> None:
    st.markdown(f"#### {tr('short_drama.role.section.list')}")
    roles = role_store.list_roles()
    if not roles:
        st.caption(tr("short_drama.role.list_empty"))
        return

    cols_per_row = 4
    for row_start in range(0, len(roles), cols_per_row):
        cols = st.columns(cols_per_row, gap="medium")
        for j in range(cols_per_row):
            idx = row_start + j
            if idx >= len(roles):
                continue
            with cols[j]:
                _render_role_card(roles[idx])


def _render_role_card(meta: RoleMeta) -> None:
    with st.container(border=True):
        if meta.role_image_path and Path(meta.role_image_path).is_file():
            st.image(meta.role_image_path, width="stretch")
        else:
            st.caption(tr("short_drama.role.card_no_image"))
        st.markdown(f"**{meta.chinese_name}** · `{meta.english_name}`")
        if meta.description:
            st.caption(meta.description)
        if meta.model:
            st.caption(f"🧠 {meta.model}")
        btn_edit, btn_del = st.columns(2)
        with btn_edit:
            if st.button(
                tr("short_drama.role.edit"),
                key=f"sd_role_edit_{meta.english_name}",
                width="stretch",
            ):
                _load_role_into_edit_form(meta)
                st.rerun()
        with btn_del:
            if st.button(
                tr("short_drama.role.delete"),
                key=f"sd_role_del_{meta.english_name}",
                width="stretch",
            ):
                role_delete_dialog(
                    meta.english_name,
                    meta.chinese_name or meta.english_name,
                )


# ---------------------------------------------------------------------------
# Form actions — profile / generation
# ---------------------------------------------------------------------------


def _read_form_fields() -> tuple[str, str, str, str, str]:
    """Return (cn_name, en_name, description, prompt, model_id)."""
    cn = (st.session_state.get(_SK_CN_NAME) or "").strip()
    en = (st.session_state.get(_SK_EN_NAME) or "").strip()
    desc = (st.session_state.get(_SK_DESC) or "").strip()
    prompt = (st.session_state.get(_SK_PROMPT) or "").strip()
    model_id = st.session_state.get(_SK_MODEL) or next(iter(IMAGE_MODEL_REGISTRY))
    return cn, en, desc, prompt, model_id


def _validate_names(cn_name: str, en_name: str) -> bool:
    if not cn_name:
        _set_edit_error(map_error("cn_name_empty"))
        st.rerun()
        return False
    ok_en, err_en = role_store.validate_english_name(en_name)
    if not ok_en:
        _set_edit_error(map_error(err_en))
        st.rerun()
        return False
    return True


def _coerce_ref_images(ref_image) -> list:
    if ref_image is None:
        return []
    if isinstance(ref_image, list):
        return ref_image
    return [ref_image]


def _limit_ref_images(ref_image) -> list:
    """Normalize uploads and cap at ``_MAX_REF_IMAGES`` (shows warning if exceeded)."""
    files = _coerce_ref_images(ref_image)
    if len(files) > _MAX_REF_IMAGES:
        st.warning(
            tr("short_drama.role.ref_image_too_many", max=_MAX_REF_IMAGES)
        )
        return files[:_MAX_REF_IMAGES]
    return files


def _configure_workflow_ref_slots(
    workflow: dict[str, Any],
    ref_count: int,
) -> list[str]:
    """Drop unused LoadImage nodes and encoder image inputs for ``ref_count`` refs (0–3)."""
    encoder = workflow.get("11")
    if not isinstance(encoder, dict):
        return []
    inputs = encoder.get("inputs")
    if not isinstance(inputs, dict):
        return []

    ref_count = max(0, min(ref_count, len(_QWEN_ROLE_REF_SLOTS)))
    active_node_ids: list[str] = []
    for i, (node_id, input_key) in enumerate(_QWEN_ROLE_REF_SLOTS):
        if i < ref_count:
            active_node_ids.append(node_id)
        else:
            workflow.pop(node_id, None)
            inputs.pop(input_key, None)
    return active_node_ids


def _apply_role_workflow_generation_params(
    workflow: dict[str, Any],
    kind: GenerationKind,
) -> None:
    """Override KSampler seed (random) and EmptyLatentImage size by generation kind."""
    sampler = workflow.get(_QWEN_ROLE_KSAMPLER_NODE_ID)
    if isinstance(sampler, dict):
        inputs = sampler.get("inputs")
        if isinstance(inputs, dict):
            inputs["seed"] = random.randint(0, 2**63 - 1)

    width, height, batch_size = _ROLE_LATENT_BY_KIND[kind]
    latent = workflow.get(_QWEN_ROLE_EMPTY_LATENT_NODE_ID)
    if isinstance(latent, dict):
        inputs = latent.get("inputs")
        if isinstance(inputs, dict):
            inputs["width"] = width
            inputs["height"] = height
            inputs["batch_size"] = batch_size


def _prepare_refs_for_comfy(ref_files: list) -> list[str]:
    """Write uploads to disposable temp paths; caller must discard after use."""
    if not ref_files:
        return []
    paths: list[str] = []
    for uploaded in ref_files:
        ref_path = role_store.prepare_ref_image_for_generation(uploaded)
        if ref_path is None:
            _set_edit_error(map_error("ref_image_save_failed"))
            st.rerun()
        paths.append(ref_path)
    return paths


def _handle_save_profile() -> None:
    cn_name, en_name, desc, _, _ = _read_form_fields()
    if not _validate_names(cn_name, en_name):
        return

    editing_en = _editing_english_name()
    if editing_en:
        if en_name != editing_en:
            _set_edit_error(map_error("en_name_invalid"))
            st.rerun()
            return
        ok, err, meta = role_store.update_role_profile(
            english_name=editing_en,
            chinese_name=cn_name,
            description=desc,
        )
        success_key = "short_drama.role.profile_updated"
    else:
        ok, err, meta = role_store.save_role_profile(
            chinese_name=cn_name,
            english_name=en_name,
            description=desc,
        )
        success_key = "short_drama.role.profile_saved"
        if ok and meta is not None:
            st.session_state[_SK_EDITING_ROLE] = meta.english_name

    if not ok or meta is None:
        _set_edit_error(map_error(err))
        st.rerun()
        return

    _set_edit_success(
        tr(success_key, name=meta.chinese_name or meta.english_name)
    )
    st.rerun()


def _queue_image_generation(kind: GenerationKind) -> None:
    """Validate form state, then rerun so the preview panel can render disabled first."""
    cn_name, en_name, _, prompt, model_id = _read_form_fields()
    if not _validate_names(cn_name, en_name):
        return

    if not role_store.is_english_name_taken(en_name):
        _set_edit_error(map_error("profile_save_required"))
        st.rerun()
        return

    if not prompt:
        _set_edit_error(map_error("prompt_empty"))
        st.rerun()
        return

    model_info = IMAGE_MODEL_REGISTRY.get(model_id)
    if model_info is None:
        _set_edit_error(map_error("model_invalid", name=model_id))
        st.rerun()
        return

    workflow_key = get_workflow_key_for_scene(model_info, "role")
    if not workflow_key:
        _set_edit_error(map_error("workflow_scene_missing", scene="role"))
        st.rerun()
        return

    st.session_state[_SK_GEN_PENDING] = kind
    st.rerun()


def _execute_image_generation(
    pixelle_video: Any,
    ref_files: list,
    kind: GenerationKind,
) -> None:
    cn_name, en_name, desc, prompt, model_id = _read_form_fields()
    if not _validate_names(cn_name, en_name):
        return

    if not role_store.is_english_name_taken(en_name):
        _set_edit_error(map_error("profile_save_required"))
        st.rerun()
        return

    if not prompt:
        _set_edit_error(map_error("prompt_empty"))
        st.rerun()
        return

    model_info = IMAGE_MODEL_REGISTRY.get(model_id)
    if model_info is None:
        _set_edit_error(map_error("model_invalid", name=model_id))
        st.rerun()
        return

    workflow_key = get_workflow_key_for_scene(model_info, "role")
    if not workflow_key:
        _set_edit_error(map_error("workflow_scene_missing", scene="role"))
        st.rerun()
        return

    workflow, wf_err, wf_fmt = load_workflow(workflow_key)
    if wf_err:
        _set_edit_error(map_error(wf_err, **wf_fmt))
        st.rerun()
        return

    ref_paths = _prepare_refs_for_comfy(ref_files)
    load_node_ids = _configure_workflow_ref_slots(workflow, len(ref_paths))

    suffix = GENERATION_PROMPT_SUFFIX.get(kind, "")
    full_prompt = f"{prompt}\n\n{suffix}" if suffix else prompt
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if isinstance(inputs, dict) and "prompt" in inputs:
            inputs["prompt"] = full_prompt

    for node_id, local_path in zip(load_node_ids, ref_paths):
        comfy_name, up_err, up_fmt = run_async(
            upload_image_to_comfy(pixelle_video, local_path)
        )
        if up_err:
            _set_edit_error(map_error(up_err, **up_fmt))
            st.rerun()
            return
        workflow[node_id]["inputs"]["image"] = comfy_name

    _apply_role_workflow_generation_params(workflow, kind)

    progress = st.progress(0, text=tr("short_drama.role.progress.starting"))
    start = time.time()

    def _on_progress(value: int, phase: str) -> None:
        phase_text = {
            "executing": tr("short_drama.role.progress.executing"),
            "downloading": tr("short_drama.role.progress.downloading"),
            "saving": tr("short_drama.role.progress.saving"),
        }.get(phase, phase)
        progress.progress(value, text=phase_text)

    try:
        try:
            result, gen_err, gen_fmt = run_async(
                execute_comfy_workflow(
                    pixelle_video=pixelle_video,
                    workflow=workflow,
                    on_progress=_on_progress,
                )
            )
            if gen_err or result is None or not result.paths:
                progress.empty()
                _set_edit_error(map_error(gen_err or "no_output", **gen_fmt))
                st.rerun()
                return
            image_local_paths = result.paths
        except Exception as exc:  # noqa: BLE001 — surface to UI
            logger.exception(exc)
            progress.empty()
            _set_edit_error(map_error("generation_failed", error=str(exc)))
            st.rerun()
            return
    finally:
        for ref_path in ref_paths:
            role_store.discard_temp_file(ref_path)

    progress.progress(100, text=tr("short_drama.role.progress.done"))
    elapsed = time.time() - start
    thumb_w, thumb_h = _preview_thumb_size(kind)
    thumb_paths = [
        _ensure_preview_thumbnail(path, thumb_w, thumb_h)
        for path in image_local_paths
    ]

    previews: list[dict] = list(st.session_state.get(_SK_PREVIEWS, []))
    previews.append(
        {
            "image_paths": list(image_local_paths),
            "thumb_paths": list(thumb_paths),
            "selected_image_index": 0,
            "chinese_name": cn_name,
            "english_name": en_name,
            "model": model_id,
            "prompt": full_prompt,
            "elapsed_sec": elapsed,
            "generation_kind": kind,
        }
    )
    st.session_state[_SK_PREVIEWS] = previews
    success_key = (
        "short_drama.role.generate_closeup_success"
        if kind == "closeup"
        else "short_drama.role.generate_three_view_success"
    )
    st.session_state[_SK_LAST_SUCCESS] = tr(success_key, seconds=f"{elapsed:.1f}")
    st.rerun()


def _generation_kind_label(kind: str) -> str:
    if kind == "three_view":
        return tr("short_drama.role.gen_kind.three_view")
    return tr("short_drama.role.gen_kind.closeup")


def _promote_preview_to_official(preview_index: int) -> None:
    previews: list[dict] = list(st.session_state.get(_SK_PREVIEWS, []))
    if preview_index < 0 or preview_index >= len(previews):
        st.session_state[_SK_LAST_ERROR] = map_error("src_missing")
        st.rerun()
        return
    item = previews[preview_index]
    paths = _preview_image_paths(item)
    sel = _preview_selected_index(item, len(paths))
    if not paths or sel < 0:
        st.session_state[_SK_LAST_ERROR] = tr("short_drama.role.preview_none_selected")
        st.rerun()
        return
    temp_image_path = paths[sel]

    en_name = (item.get("english_name") or "").strip()
    if not en_name or not role_store.is_english_name_taken(en_name):
        st.session_state[_SK_LAST_ERROR] = map_error("role_missing", name=en_name)
        st.rerun()
        return
    kind = item.get("generation_kind") or "closeup"
    ok, err, final_path = role_store.promote_temp_to_role_asset(
        english_name=en_name,
        temp_image_path=temp_image_path,
        asset=kind,
    )
    if not ok:
        st.session_state[_SK_LAST_ERROR] = map_error(err)
        st.rerun()
        return

    for path in paths:
        if path != temp_image_path:
            role_store.discard_temp_file(path)

    promote_key = (
        "short_drama.role.promote_three_view_success"
        if kind == "three_view"
        else "short_drama.role.promote_success"
    )
    st.session_state[_SK_LAST_SUCCESS] = tr(
        promote_key,
        name=item.get("chinese_name") or en_name,
        path=final_path,
    )
    previews.pop(preview_index)
    st.session_state[_SK_PREVIEWS] = previews
    st.rerun()
