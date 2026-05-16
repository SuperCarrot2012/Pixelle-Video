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
Small stateless helpers and layout constants for Short Drama UI.
"""

from __future__ import annotations

import hashlib

PROJECT_CARDS_PER_ROW = 4
PROJECT_CARD_PATH_DISPLAY_LEN = 32


def dialog_widget_suffix(root_path: str) -> str:
    """Stable, short suffix used to scope dialog widget keys per project."""
    return hashlib.md5(root_path.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def project_card_token(root_path: str) -> str:
    """Stable, short token used to scope card widget keys per project."""
    return hashlib.md5(root_path.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def truncate_middle(s: str, max_len: int) -> str:
    """Shorten a long string by replacing its middle with an ellipsis."""
    if len(s) <= max_len:
        return s
    half = (max_len - 3) // 2
    return s[:half] + "..." + s[-(max_len - 3 - half):]
