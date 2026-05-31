"""Create JianYing drafts from standard MP4 files."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .media_validator import validate_video
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


def create_extracted_draft(draft_root: str | Path, mp4_path: str | Path, source_name: str) -> CreatedDraft:
    root = Path(draft_root)
    source = Path(mp4_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Draft directory does not exist: {root}")
    if not source.is_file():
        raise FileNotFoundError(f"MP4 does not exist: {source}")
    video = validate_video(source)
    if video is None:
        raise ValueError(f"MP4 is not a standard importable video: {source}")

    draft_name, draft_path = reserve_unique_draft_path(root, source_name)
    media_dir = draft_path / "Resources" / "local"
    media_dir.mkdir(parents=True, exist_ok=True)
    copied = media_dir / source.name
    shutil.copy2(source, copied)
    _write_minimal_draft_files(
        draft_path,
        draft_name,
        copied,
        width=int(video.width or 1920),
        height=int(video.height or 1080),
        duration_us=int(round(float(video.duration_ms or 1000) * 1000)),
    )
    return CreatedDraft(draft_path=draft_path, draft_name=draft_name)


def _write_minimal_draft_files(
    draft_path: Path,
    draft_name: str,
    media_path: Path,
    *,
    width: int,
    height: int,
    duration_us: int,
) -> None:
    material_id = uuid4().hex
    content = {
        "id": str(uuid4()).upper(),
        "name": draft_name,
        "duration": duration_us,
        "fps": 30,
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
