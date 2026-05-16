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
Error key → i18n mapping for Short Drama project operations.
"""

from __future__ import annotations

from web.i18n import tr

_ERR_I18N: dict[str, str] = {
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
    "not_found": "short_drama.project.err.not_found",
    "rmtree_failed": "short_drama.project.err.rmtree",
    "move_target_exists": "short_drama.project.err.move_target_exists",
    "move_into_self": "short_drama.project.err.move_into_self",
    "move_parent_missing": "short_drama.project.err.move_parent_missing",
    "move_failed": "short_drama.project.err.move_failed",
}


def map_project_error(err: str) -> str:
    """Translate a project_store error key to a localized message."""
    key = _ERR_I18N.get(err, "short_drama.project.err.path_resolve")
    return tr(key)
