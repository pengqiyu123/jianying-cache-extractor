"""Create JianYing drafts from extracted cache MP4 files."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pyJianYingDraft as draft

from .media_validator import inspect_video, verify_copy
from .models import CreatedDraft


def safe_draft_name(value: str) -> str:
    """Return a Windows-safe, JianYing-friendly draft name fragment."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:48] or "cache"


def unique_draft_name(draft_dir: Path, source_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"提取_{safe_draft_name(source_name)}_{timestamp}"
    name = base
    suffix = 1
    while (draft_dir / name).exists():
        suffix += 1
        name = f"{base}_{suffix}"
    return name


def reserve_unique_draft_path(draft_dir: Path, source_name: str) -> tuple[str, Path]:
    """Create and reserve a unique draft directory atomically."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"提取_{safe_draft_name(source_name)}_{timestamp}"
    for suffix in ["", *[f"_{index}" for index in range(2, 10)]]:
        name = f"{base}{suffix}"
        path = draft_dir / name
        try:
            path.mkdir(parents=False, exist_ok=False)
            return name, path
        except FileExistsError:
            continue

    name = f"{base}_{uuid4().hex[:8]}"
    path = draft_dir / name
    path.mkdir(parents=False, exist_ok=False)
    return name, path


def create_extracted_draft(
    draft_dir: str | Path,
    mp4_path: str | Path,
    source_name: str,
    *,
    fps: int = 30,
) -> CreatedDraft:
    """Copy an MP4 cache into a new draft and place it on a video track."""
    root = Path(draft_dir)
    source = Path(mp4_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Draft directory does not exist: {root}")
    if not source.is_file():
        raise FileNotFoundError(f"MP4 cache does not exist: {source}")
    if source.stat().st_size <= 0:
        raise ValueError(f"MP4 cache is empty: {source}")
    if inspect_video(source) is None:
        raise ValueError(
            f"MP4 cache is not an importable video: {source}. "
            "The file may be an internal/encrypted JianYing cache blob."
        )

    probe_material = draft.VideoMaterial(str(source))
    width = int(getattr(probe_material, "width", 0) or 1920)
    height = int(getattr(probe_material, "height", 0) or 1080)
    duration = int(getattr(probe_material, "duration", 0) or 1_000_000)

    draft_name, draft_path = reserve_unique_draft_path(root, source_name)
    try:
        draft_path.rmdir()
        draft_folder = draft.DraftFolder(str(root))
        script = draft_folder.create_draft(draft_name, width, height, fps=fps, allow_replace=False)
        media_dir = draft_path / "Resources" / "extracted"
        media_dir.mkdir(parents=True, exist_ok=False)
        copied_path = media_dir / source.name
        shutil.copy2(source, copied_path)
        verification = verify_copy(source, copied_path)
        if not verification.size_verified:
            raise IOError(f"Copied file size mismatch: {source} -> {copied_path}")

        material = draft.VideoMaterial(str(copied_path))
        script.add_track(draft.TrackType.video)
        script.add_segment(draft.VideoSegment(material, draft.trange(0, duration)))
        script.save()

        content_path = draft_path / "draft_content.json"
        meta_path = draft_path / "draft_meta_info.json"
        if not content_path.exists() or not meta_path.exists():
            raise IOError("Draft files were not created completely.")

        return CreatedDraft(
            name=draft_name,
            draft_path=draft_path,
            media_path=copied_path,
            source_media_path=source,
            size_verified=verification.size_verified,
            sha256=verification.sha256,
        )
    except Exception:
        if draft_path.exists():
            shutil.rmtree(draft_path, ignore_errors=True)
        raise
