"""Create JianYing drafts from standard MP4 files."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

try:  # pragma: no cover - exercised through monkeypatched fakes in tests.
    import pyJianYingDraft as draft
except Exception:  # pragma: no cover - fallback keeps the tool usable in tests.
    draft = None

from .media_validator import inspect_video, verify_copy
from .models import CreatedDraft


def safe_draft_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:48] or "cache"


def reserve_unique_draft_path(draft_root: str | Path, source_name: str) -> tuple[str, Path]:
    root = Path(draft_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"提取_{safe_draft_name(source_name)}_{timestamp}"
    for suffix in ["", *[f"_{index}" for index in range(2, 20)]]:
        name = f"{base}{suffix}"
        path = root / name
        try:
            path.mkdir(parents=True, exist_ok=False)
            return name, path
        except FileExistsError:
            continue
    name = f"{base}_{uuid4().hex[:8]}"
    path = root / name
    path.mkdir(parents=True, exist_ok=False)
    return name, path


def create_extracted_draft(draft_root: str | Path, mp4_path: str | Path, source_name: str, *, fps: int = 30) -> CreatedDraft:
    root = Path(draft_root)
    source = Path(mp4_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Draft directory does not exist: {root}")
    if not source.is_file():
        raise FileNotFoundError(f"MP4 does not exist: {source}")
    video = inspect_video(source)
    if video is None:
        raise ValueError(f"MP4 is not a standard importable video: {source}")

    width, height, duration_ms = _shape(video)
    width = int(width or 1920)
    height = int(height or 1080)
    duration_us = int(round(float(duration_ms or 1000) * 1000))
    draft_name = reserve_unique_draft_name(root, source_name)
    draft_path: Path | None = None
    try:
        if draft is not None:
            draft_folder = draft.DraftFolder(root)
            script = draft_folder.create_draft(draft_name, width, height, fps=fps, allow_replace=False)
            draft_path = Path(getattr(script, "draft_path", root / draft_name))
            media_path = _copy_media(source, draft_path)
            _add_video_segment(script, media_path, duration_us)
            script.save()
        else:
            draft_path = root / draft_name
            draft_path.mkdir(parents=True, exist_ok=False)
            media_path = _copy_media(source, draft_path)
            _write_minimal_draft_files(
                draft_path,
                draft_name,
                media_path,
                width=width,
                height=height,
                duration_us=duration_us,
                fps=fps,
            )
        _ensure_draft_files(draft_path)
        copied = verify_copy(source, media_path)
        return CreatedDraft(
            name=draft_name,
            draft_path=draft_path,
            media_path=media_path,
            source_media_path=source,
            size_verified=copied.size_verified,
        )
    except Exception:
        if draft_path is not None and draft_path.exists():
            shutil.rmtree(draft_path, ignore_errors=True)
        raise


def reserve_unique_draft_name(draft_root: str | Path, source_name: str) -> str:
    root = Path(draft_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"提取_{safe_draft_name(source_name)}_{timestamp}"
    for suffix in ["", *[f"_{index}" for index in range(2, 20)]]:
        name = f"{base}{suffix}"
        if not (root / name).exists():
            return name
    return f"{base}_{uuid4().hex[:8]}"


def _copy_media(source: Path, draft_path: Path) -> Path:
    media_dir = draft_path / "Resources" / "extracted"
    media_dir.mkdir(parents=True, exist_ok=True)
    target = media_dir / source.name
    shutil.copy2(source, target)
    return target


def _add_video_segment(script, media_path: Path, duration_us: int) -> None:
    material = draft.VideoMaterial(media_path)
    track = script.add_track(draft.TrackType.video)
    segment = draft.VideoSegment(material, draft.trange(0, duration_us))
    track.add_segment(segment)


def _ensure_draft_files(draft_path: Path) -> None:
    missing = [name for name in ("draft_content.json", "draft_meta_info.json") if not (draft_path / name).exists()]
    if missing:
        raise RuntimeError(f"Draft creation incomplete: missing {', '.join(missing)}")


def _shape(info) -> tuple[int | None, int | None, float | None]:
    if isinstance(info, tuple):
        return info[0], info[1], info[2]
    return getattr(info, "width", None), getattr(info, "height", None), getattr(info, "duration_ms", None)


def _write_minimal_draft_files(
    draft_path: Path,
    draft_name: str,
    media_path: Path,
    *,
    width: int,
    height: int,
    duration_us: int,
    fps: int = 30,
) -> None:
    material_id = uuid4().hex
    content = {
        "id": str(uuid4()).upper(),
        "name": draft_name,
        "duration": duration_us,
        "fps": fps,
        "canvas_config": {"width": width, "height": height, "ratio": "original"},
        "materials": {
            "videos": [
                {
                    "id": material_id,
                    "type": "video",
                    "path": str(media_path),
                    "duration": duration_us,
                    "width": width,
                    "height": height,
                }
            ]
        },
        "tracks": [
            {
                "id": uuid4().hex,
                "type": "video",
                "segments": [
                    {
                        "id": uuid4().hex,
                        "material_id": material_id,
                        "target_timerange": {"start": 0, "duration": duration_us},
                    }
                ],
            }
        ],
    }
    meta = {
        "draft_name": draft_name,
        "draft_root_path": str(draft_path),
        "tm_duration": duration_us,
    }
    (draft_path / "draft_content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    (draft_path / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
