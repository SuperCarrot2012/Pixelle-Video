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
Error key → i18n mapping for all Short Drama operations.

Store modules and ``comfy_service`` return short string error codes. UI code
passes those codes to :func:`map_error` for localized messages.

If you add a new error code in a store, register it in :data:`_ERR_I18N`
below. Keys MUST be globally unique across all stores — namespace your new
keys with the resource prefix (e.g. ``role_*``, ``prop_*``) when there is any
risk of collision with another store's error codes.
"""

from __future__ import annotations

from web.i18n import tr

# Default i18n key used when an unknown error code is looked up.
_DEFAULT_FALLBACK_KEY = "short_drama.err.unknown"


_ERR_I18N: dict[str, str] = {
    # ----- project_store -----
    "name_empty": "short_drama.project.err.name_empty",
    "empty": "short_drama.project.err.path_empty",
    "backslash": "short_drama.project.err.path_backslash",
    "not_absolute": "short_drama.project.err.path_not_absolute",
    "null_byte": "short_drama.project.err.path_null",
    "newline": "short_drama.project.err.path_newline",
    "resolve_failed": "short_drama.project.err.path_resolve",
    "forbidden_root": "short_drama.project.err.path_forbidden",
    "already_exists": "short_drama.project.err.already_exists",
    "mkdir_failed": "short_drama.project.err.mkdir",
    "write_failed": "short_drama.project.err.write",
    "project_not_found": "short_drama.project.err.not_found",
    "rmtree_failed": "short_drama.project.err.rmtree",
    "move_target_exists": "short_drama.project.err.move_target_exists",
    "move_into_self": "short_drama.project.err.move_into_self",
    "move_parent_missing": "short_drama.project.err.move_parent_missing",
    "move_failed": "short_drama.project.err.move_failed",
    # ----- role_store / role_page -----
    "cn_name_empty": "short_drama.role.err.cn_name_empty",
    "en_name_empty": "short_drama.role.err.en_name_empty",
    "en_name_invalid": "short_drama.role.err.en_name_invalid",
    "en_name_duplicated": "short_drama.role.err.en_name_duplicated",
    "no_project": "short_drama.work.no_project",
    "role_write_failed": "short_drama.role.err.write_failed",
    "role_not_found": "short_drama.role.err.not_found",
    "role_delete_failed": "short_drama.role.err.delete_failed",
    "src_missing": "short_drama.role.err.preview_missing",
    "copy_failed": "short_drama.role.err.copy_failed",
    "profile_save_required": "short_drama.role.err.profile_save_required",
    "asset_invalid": "short_drama.role.err.unknown",
    "prompt_empty": "short_drama.role.err.prompt_empty",
    "model_invalid": "short_drama.role.err.model_invalid",
    "ref_image_save_failed": "short_drama.role.err.ref_image_save_failed",
    "role_missing": "short_drama.role.err.role_missing",
    "generation_failed": "short_drama.role.err.generation_failed",
    # ----- comfy_service (web/short_drama/workflow/) -----
    "ref_upload_failed": "short_drama.comfy.err.ref_upload_failed",
    "workflow_key_invalid": "short_drama.comfy.err.workflow_key_invalid",
    "workflow_missing": "short_drama.comfy.err.workflow_missing",
    "workflow_unreadable": "short_drama.comfy.err.workflow_unreadable",
    "workflow_invalid": "short_drama.comfy.err.workflow_invalid",
    "temp_write_failed": "short_drama.comfy.err.temp_write_failed",
    "no_output": "short_drama.comfy.err.no_output",
    "execution_failed": "short_drama.comfy.err.execution_failed",
    "workflow_scene_missing": "short_drama.comfy.err.scene_missing",
}


def error_i18n_key(err: str) -> str:
    """Return the i18n key for ``err``; unknown codes use the default fallback key."""
    return _ERR_I18N.get(err, _DEFAULT_FALLBACK_KEY)


def map_error(err: str, **fmt: str) -> str:
    """Translate a short-drama error code to a localized message."""
    key = error_i18n_key(err)
    if fmt:
        return tr(key, **fmt)
    return tr(key)
