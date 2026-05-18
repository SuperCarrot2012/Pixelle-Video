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
- ComfyUI execution: ``web.short_drama.comfy_image`` (not ``pixelle_video.media``).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from loguru import logger

from web.i18n import tr
from web.short_drama import role_store
from web.short_drama.comfy_image import (
    ComfyImageGenerationError,
    execute_comfy_image_workflow,
    validate_workflow,
)
from web.short_drama.dialogs import role_delete_dialog
from web.short_drama.errors import map_error
from web.short_drama.models import IMAGE_MODEL_REGISTRY
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

    left, right = st.columns([1, 1], gap="medium")
    with left:
        _render_edit_form(pixelle_video)
    with right:
        _render_preview_panel()


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
            accept_multiple_files=False,
            help=tr("short_drama.role.ref_image_help"),
            key="sd_role_ref_image",
        )

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
                _handle_image_generation(pixelle_video, ref_image, "closeup")
        with btn_three:
            if st.button(
                tr("short_drama.role.generate_three_view"),
                key="sd_role_generate_three_view_btn",
                width="stretch",
            ):
                _handle_image_generation(pixelle_video, ref_image, "three_view")
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
    """Render preset prompt-template buttons just above the prompt textarea.

    Buttons sit in a fixed N-per-row grid so a single template won't stretch
    across the whole column; additional templates wrap to the next row.
    """
    st.caption(tr("short_drama.role.prompt_templates"))
    buttons_per_row = 8
    for row_start in range(0, len(PROMPT_TEMPLATES), buttons_per_row):
        cols = st.columns(buttons_per_row)
        for j in range(buttons_per_row):
            idx = row_start + j
            if idx >= len(PROMPT_TEMPLATES):
                continue
            tmpl = PROMPT_TEMPLATES[idx]
            with cols[j]:
                if st.button(
                    tmpl["label"],
                    key=f"sd_role_tmpl_{tmpl['id']}",
                    width="stretch",
                ):
                    st.session_state[_SK_PROMPT] = tmpl["text"]
                    st.rerun()


# ---------------------------------------------------------------------------
# Right column — preview panel
# ---------------------------------------------------------------------------


def _render_preview_panel() -> None:
    st.markdown(f"#### {tr('short_drama.role.section.preview')}")
    with st.container(border=True):
        previews: list[dict] = st.session_state.get(_SK_PREVIEWS, [])
        if not previews:
            st.info(tr("short_drama.role.preview_empty"))
            # Reserve some visual space even when empty.
            st.markdown("&nbsp;\n\n&nbsp;\n\n&nbsp;", unsafe_allow_html=True)
            return

        # Newest first.
        for i, item in enumerate(reversed(previews)):
            idx = len(previews) - 1 - i
            kind = item.get("generation_kind") or "closeup"
            st.image(
                item["image_path"],
                caption=tr(
                    "short_drama.role.preview_caption",
                    cn=item.get("chinese_name") or "-",
                    en=item.get("english_name") or "-",
                    model=item.get("model") or "-",
                    kind=_generation_kind_label(kind),
                ),
                width="stretch",
            )
            a, b = st.columns([3, 1])
            with a:
                st.caption(
                    tr(
                        "short_drama.role.preview_source",
                        path=item["image_path"],
                    )
                )
            with b:
                if st.button(
                    tr("short_drama.role.preview_promote"),
                    key=f"sd_role_promote_{idx}",
                    type="primary",
                    width="stretch",
                ):
                    _promote_preview_to_official(idx)
            st.divider()

        if st.button(
            tr("short_drama.role.preview_clear"),
            key="sd_role_preview_clear",
        ):
            st.session_state[_SK_PREVIEWS] = []
            st.rerun()


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


def _prepare_ref_for_comfy(ref_image) -> Optional[str]:
    """Return a disposable local path for ComfyUI; caller must discard after use."""
    if ref_image is None:
        return None
    ref_path = role_store.prepare_ref_image_for_generation(ref_image)
    if ref_path is None:
        _set_edit_error(map_error("ref_image_save_failed"))
        st.rerun()
    return ref_path


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


def _handle_image_generation(
    pixelle_video: Any,
    ref_image,
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

    workflow_key = model_info["workflow_key"]
    wf_ok, wf_err = _check_workflow_ready(workflow_key)
    if not wf_ok:
        _set_edit_error(wf_err)
        st.rerun()
        return

    ref_path = _prepare_ref_for_comfy(ref_image)
    if ref_image is not None and ref_path is None:
        return

    if model_info.get("requires_ref_image") and not ref_path:
        _set_edit_error(map_error("ref_image_required"))
        st.rerun()
        return

    suffix = GENERATION_PROMPT_SUFFIX.get(kind, "")
    full_prompt = f"{prompt}\n\n{suffix}" if suffix else prompt

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
            image_local_path = run_async(
                execute_comfy_image_workflow(
                    pixelle_video=pixelle_video,
                    workflow_key=workflow_key,
                    prompt=full_prompt,
                    ref_image_path=ref_path,
                    ref_image_param=model_info.get("ref_image_param", "image"),
                    on_progress=_on_progress,
                )
            )
        except ComfyImageGenerationError as exc:
            progress.empty()
            _set_edit_error(map_error(exc.code, **exc.fmt))
            st.rerun()
            return
        except Exception as exc:  # noqa: BLE001 — surface to UI
            logger.exception(exc)
            progress.empty()
            _set_edit_error(map_error("generation_failed", error=str(exc)))
            st.rerun()
            return
    finally:
        role_store.discard_temp_file(ref_path)

    progress.progress(100, text=tr("short_drama.role.progress.done"))
    elapsed = time.time() - start

    existing = role_store.load_role(en_name)
    if existing is not None:
        existing.chinese_name = cn_name
        existing.description = desc
        role_store.update_role(existing)

    previews: list[dict] = list(st.session_state.get(_SK_PREVIEWS, []))
    previews.append(
        {
            "image_path": image_local_path,
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
    en_name = (item.get("english_name") or "").strip()
    if not en_name or not role_store.is_english_name_taken(en_name):
        st.session_state[_SK_LAST_ERROR] = map_error("role_missing", name=en_name)
        st.rerun()
        return
    kind = item.get("generation_kind") or "closeup"
    ok, err, final_path = role_store.promote_temp_to_role_asset(
        english_name=en_name,
        temp_image_path=item["image_path"],
        asset=kind,
    )
    if not ok:
        st.session_state[_SK_LAST_ERROR] = map_error(err)
        st.rerun()
        return

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
    # Drop just this preview entry — keep siblings so the user can compare.
    previews.pop(preview_index)
    st.session_state[_SK_PREVIEWS] = previews
    st.rerun()


# ---------------------------------------------------------------------------
# Workflow / generation helpers
# ---------------------------------------------------------------------------


def _check_workflow_ready(workflow_key: str) -> tuple[bool, str]:
    """Make sure the workflow JSON exists and (for RunningHub) has an ID."""
    ok, err_key, fmt = validate_workflow(workflow_key)
    if ok:
        return True, ""
    return False, map_error(err_key, **fmt)

