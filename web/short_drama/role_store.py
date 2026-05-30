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
Short Drama — Role (角色) persistence layer.

Layout under the active project root:

    <project_root>/
        roles/
            <english_name>/
                role.json        # metadata
                role.<ext>       # official selected image (after confirm)
        temp/                    # working/preview images (hash-named cache)

The English name is the project-unique identifier; the Chinese name is for
display only. All filesystem I/O is contained here so role_page.py can focus
on UI concerns.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from web.short_drama.work_context import get_work_path

TEMP_DIRNAME = "temp"
ROLES_DIRNAME = "roles"
ROLE_METADATA_FILENAME = "role.json"
ROLE_SCHEMA_VERSION = 1

# Conservative english-name rule: letters/digits/underscore/hyphen, 1-64 chars.
_EN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,63}$")


@dataclass
class RoleMeta:
    """Role metadata persisted to <project>/roles/<en_name>/role.json."""

    chinese_name: str
    english_name: str
    description: str
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = ROLE_SCHEMA_VERSION
    extra: dict = field(default_factory=dict)

    @property
    def role_image_path(self) -> str:
        closeup = (self.extra or {}).get("closeup_generation") or {}
        return str(closeup.get("saved_path") or "")

    @property
    def three_view_image_path(self) -> str:
        three_view = (self.extra or {}).get("three_view_generation") or {}
        return str(three_view.get("saved_path") or "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _project_root() -> Optional[Path]:
    base = get_work_path()
    return Path(base) if base else None


def roles_root() -> Optional[Path]:
    base = _project_root()
    return base / ROLES_DIRNAME if base else None


def temp_root() -> Optional[Path]:
    rr = roles_root()
    return rr / TEMP_DIRNAME if rr else None


def ensure_dirs() -> tuple[Optional[Path], Optional[Path]]:
    """Make sure roles/ and roles/temp/ exist under the active project root."""
    base = _project_root()
    if base is None:
        return None, None
    roles_p = base / ROLES_DIRNAME
    temp_p = roles_p / TEMP_DIRNAME
    roles_p.mkdir(parents=True, exist_ok=True)
    temp_p.mkdir(parents=True, exist_ok=True)
    return roles_p, temp_p


def _role_dir_for(english_name: str) -> Optional[Path]:
    rr = roles_root()
    if rr is None:
        return None
    return rr / english_name


def validate_english_name(name: str) -> tuple[bool, str]:
    """Validate English name format (returns (ok, error_key))."""
    if not name or not name.strip():
        return False, "en_name_empty"
    if not _EN_NAME_RE.match(name.strip()):
        return False, "en_name_invalid"
    return True, ""


def is_english_name_taken(english_name: str) -> bool:
    d = _role_dir_for(english_name)
    if d is None:
        return False
    return (d / ROLE_METADATA_FILENAME).is_file()


def list_roles() -> list[RoleMeta]:
    """Scan <project>/roles/*/role.json and return all roles, newest first."""
    rr = roles_root()
    if rr is None or not rr.is_dir():
        return []
    out: list[RoleMeta] = []
    for entry in rr.iterdir():
        if not entry.is_dir() or entry.name == TEMP_DIRNAME:
            continue
        meta = load_role(entry.name)
        if meta is not None:
            out.append(meta)
    out.sort(key=lambda m: m.updated_at or m.created_at, reverse=True)
    return out


def load_role(english_name: str) -> Optional[RoleMeta]:
    d = _role_dir_for(english_name)
    if d is None:
        return None
    pj = d / ROLE_METADATA_FILENAME
    if not pj.is_file():
        return None
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return RoleMeta(
        chinese_name=str(data.get("chinese_name", "")),
        english_name=str(data.get("english_name", english_name)),
        description=str(data.get("description", "")),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        schema_version=int(data.get("schema_version", ROLE_SCHEMA_VERSION)),
        extra=dict(data.get("extra") or {}),
    )


def _write_metadata(meta: RoleMeta) -> bool:
    d = _role_dir_for(meta.english_name)
    if d is None:
        return False
    d.mkdir(parents=True, exist_ok=True)
    payload = asdict(meta)
    try:
        (d / ROLE_METADATA_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def create_role(
    chinese_name: str,
    english_name: str,
    description: str,
) -> tuple[bool, str, Optional[RoleMeta]]:
    """Create a brand-new role record (no image yet).

    Returns (ok, error_key, meta).
    """
    cn = (chinese_name or "").strip()
    en = (english_name or "").strip()
    if not cn:
        return False, "cn_name_empty", None
    ok, err = validate_english_name(en)
    if not ok:
        return False, err, None
    if is_english_name_taken(en):
        return False, "en_name_duplicated", None

    roles_p, _ = ensure_dirs()
    if roles_p is None:
        return False, "no_project", None

    now = _now_iso()
    meta = RoleMeta(
        chinese_name=cn,
        english_name=en,
        description=(description or "").strip(),
        created_at=now,
        updated_at=now,
    )
    if not _write_metadata(meta):
        return False, "role_write_failed", None
    return True, "", meta


def save_role_profile(
    chinese_name: str,
    english_name: str,
    description: str,
) -> tuple[bool, str, Optional[RoleMeta]]:
    """Create ``role.json`` from form fields (no image generation)."""
    cn = (chinese_name or "").strip()
    en = (english_name or "").strip()
    if not cn:
        return False, "cn_name_empty", None
    ok, err = validate_english_name(en)
    if not ok:
        return False, err, None

    desc_s = (description or "").strip()

    if is_english_name_taken(en):
        return False, "en_name_duplicated", None

    return create_role(
        chinese_name=cn,
        english_name=en,
        description=desc_s,
    )


def update_role_profile(
    english_name: str,
    chinese_name: str,
    description: str,
) -> tuple[bool, str, Optional[RoleMeta]]:
    """Update display fields on an existing role (English name is immutable)."""
    cn = (chinese_name or "").strip()
    if not cn:
        return False, "cn_name_empty", None
    en = (english_name or "").strip()
    meta = load_role(en)
    if meta is None:
        return False, "role_not_found", None
    meta.chinese_name = cn
    meta.description = (description or "").strip()
    ok, err = update_role(meta)
    return (ok, err, meta if ok else None)


def update_role(meta: RoleMeta) -> tuple[bool, str]:
    """Update an existing role's metadata (refreshes updated_at)."""
    if not is_english_name_taken(meta.english_name):
        return False, "role_not_found"
    meta.updated_at = _now_iso()
    if not _write_metadata(meta):
        return False, "role_write_failed"
    return True, ""


def delete_role(english_name: str) -> tuple[bool, str]:
    d = _role_dir_for(english_name)
    if d is None or not d.is_dir():
        return False, "role_not_found"
    try:
        shutil.rmtree(d)
        return True, ""
    except OSError:
        return False, "role_delete_failed"


def _safe_ext_from_bytes(data: bytes, fallback: str = ".png") -> str:
    """Pick a sane file extension by sniffing magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ".gif"
    if data.startswith(b"BM"):
        return ".bmp"
    return fallback


def _safe_ext_from_filename(filename: str, fallback: str = ".png") -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return ".jpg" if ext == ".jpeg" else ext
    return fallback


def save_bytes_to_temp(
    data: bytes,
    prefer_ext: Optional[str] = None,
    original_filename: Optional[str] = None,
) -> Optional[str]:
    """Save raw bytes to <project>/roles/temp/<sha1>.<ext> and return absolute path.

    Returns None if no active project.
    """
    _, temp_p = ensure_dirs()
    if temp_p is None:
        return None
    digest = hashlib.sha1(data, usedforsecurity=False).hexdigest()
    if prefer_ext:
        ext = prefer_ext if prefer_ext.startswith(".") else f".{prefer_ext}"
    elif original_filename:
        ext = _safe_ext_from_filename(original_filename)
    else:
        ext = _safe_ext_from_bytes(data)
    out = temp_p / f"{digest}{ext}"
    if not out.is_file():
        try:
            out.write_bytes(data)
        except OSError:
            return None
    return str(out.resolve())


def prepare_ref_image_for_generation(uploaded_file) -> Optional[str]:
    """Write upload to a disposable temp file for one ComfyUI run (not cached)."""
    if uploaded_file is None:
        return None
    try:
        data = uploaded_file.getbuffer().tobytes()
    except (AttributeError, TypeError):
        data = uploaded_file.read()
    if not data:
        return None
    _, temp_p = ensure_dirs()
    if temp_p is None:
        return None
    name = getattr(uploaded_file, "name", None)
    if name:
        ext = _safe_ext_from_filename(name)
    else:
        ext = _safe_ext_from_bytes(data)
    out = temp_p / f"ref_{uuid.uuid4().hex}{ext}"
    try:
        out.write_bytes(data)
    except OSError:
        return None
    return str(out.resolve())


def discard_temp_file(path: Optional[str]) -> None:
    """Remove a one-off temp file (e.g. generation-only reference image)."""
    if not path:
        return
    try:
        p = Path(path)
        if p.is_file():
            p.unlink()
    except OSError:
        pass


def clear_temp_dir() -> bool:
    """Remove all role-generation temp files under <project>/roles/temp/."""
    temp_p = temp_root()
    if temp_p is None:
        return False
    if temp_p.is_dir():
        try:
            shutil.rmtree(temp_p)
        except OSError:
            return False
    try:
        temp_p.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return True


def _normalise_source_paths(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(path) for path in raw if path]
    if raw:
        return [str(raw)]
    return []


def _promote_source_images(
    role_dir: Path,
    english_name: str,
    asset_suffix: str,
    source_paths: list[str],
) -> tuple[Optional[list[str]], str]:
    """Copy reference images into the role dir and return persisted paths."""
    for prev in role_dir.glob(f"{english_name}-{asset_suffix}-source-*"):
        if prev.is_file():
            try:
                prev.unlink()
            except OSError:
                return None, "copy_failed"

    copied: list[str] = []
    for idx, source_path in enumerate(source_paths):
        src = Path(source_path)
        if not src.is_file():
            continue
        ext = src.suffix.lower() or ".png"
        dst = role_dir / f"{english_name}-{asset_suffix}-source-{idx}{ext}"
        try:
            shutil.copy2(src, dst)
        except OSError:
            return None, "copy_failed"
        copied.append(str(dst.resolve()))
    return copied, ""


def promote_temp_to_role_image(
    english_name: str,
    temp_image_path: str,
) -> tuple[bool, str, str]:
    """Copy a temp image to ``roles/<en>/role.<ext>`` (特写立绘)."""
    return promote_temp_to_role_asset(english_name, temp_image_path, asset="closeup")


def promote_temp_to_role_asset(
    english_name: str,
    temp_image_path: str,
    *,
    asset: str = "closeup",
    generation_info: Optional[dict] = None,
) -> tuple[bool, str, str]:
    """Copy a temp preview image into the role directory.

    ``asset`` is ``closeup`` or ``three_view``.

    Returns (ok, error_key, final_path).
    """
    if asset not in ("closeup", "three_view"):
        return False, "asset_invalid", ""

    d = _role_dir_for(english_name)
    if d is None:
        return False, "no_project", ""
    if not is_english_name_taken(english_name):
        return False, "role_not_found", ""
    src = Path(temp_image_path)
    if not src.is_file():
        return False, "src_missing", ""

    suffix = "closeup" if asset == "closeup" else "three-view"
    dst = d / f"{english_name}-{suffix}.png"

    for prev in d.glob(f"{english_name}-{suffix}.*"):
        if prev != dst:
            try:
                prev.unlink()
            except OSError:
                pass

    try:
        shutil.copy2(src, dst)
    except OSError:
        return False, "copy_failed", ""

    meta = load_role(english_name)
    if meta is None:
        return False, "role_not_found", ""
    resolved = str(dst.resolve())
    meta.extra = dict(meta.extra or {})
    source_paths = _normalise_source_paths((generation_info or {}).get("source_path"))
    promoted_sources, source_err = _promote_source_images(
        d,
        english_name,
        suffix,
        source_paths,
    )
    if promoted_sources is None:
        return False, source_err, ""
    meta.extra[f"{asset}_generation"] = {
        "generation_kind": asset,
        "prompt": str((generation_info or {}).get("prompt") or ""),
        "model": str((generation_info or {}).get("model") or ""),
        "source_path": promoted_sources,
        "saved_path": resolved,
    }
    meta.updated_at = _now_iso()
    if not _write_metadata(meta):
        return False, "role_write_failed", ""
    return True, "", resolved
