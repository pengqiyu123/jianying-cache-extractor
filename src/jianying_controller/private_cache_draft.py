"""Create drafts for JianYing private combination caches."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from .draft_creator import reserve_unique_draft_path, safe_draft_name
from .media_validator import validate_video
from .models import CreatedDraft


def create_private_cache_draft(
    draft_root: str | Path,
    mp4_path: str | Path,
    source_name: str,
    *,
    width: int | None = None,
    height: int | None = None,
    duration_us: int | None = None,
) -> CreatedDraft:
    root = Path(draft_root)
    source = Path(mp4_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Draft directory does not exist: {root}")
    if not source.is_file():
        raise FileNotFoundError(f"Private cache MP4 does not exist: {source}")
    if source.name.lower().endswith(".alpha.mp4"):
        raise ValueError("Alpha sidecar is not the main cache file.")

    width, height, duration_us = _resolve_shape(source, width=width, height=height, duration_us=duration_us)
    draft_name, draft_path = reserve_unique_draft_path(root, f"导入_{safe_draft_name(source_name)}")
    media_dir = draft_path / "Resources" / "combination"
    media_dir.mkdir(parents=True, exist_ok=True)
    copied = media_dir / source.name
    shutil.copy2(source, copied)
    alpha = source.with_name(f"{source.name}.alpha.mp4")
    if alpha.is_file():
        shutil.copy2(alpha, media_dir / alpha.name)
    _write_private_files(draft_path, draft_name, copied, width=width, height=height, duration_us=duration_us)
    return CreatedDraft(
        name=draft_name,
        draft_path=draft_path,
        media_path=copied,
        source_media_path=source,
        size_verified=copied.exists() and copied.stat().st_size == source.stat().st_size,
    )


def _resolve_shape(
    source: Path,
    *,
    width: int | None,
    height: int | None,
    duration_us: int | None,
) -> tuple[int, int, int]:
    sidecar = source.with_name(f"{source.name}.alpha.mp4")
    info = validate_video(sidecar) if sidecar.is_file() else None
    resolved_width = width or (info[0] if isinstance(info, tuple) else getattr(info, "width", None))
    resolved_height = height or (info[1] if isinstance(info, tuple) else getattr(info, "height", None))
    duration_ms = info[2] if isinstance(info, tuple) else getattr(info, "duration_ms", None)
    resolved_duration = duration_us or int(round(float(duration_ms or 60_000) * 1000))
    return int(resolved_width or 1920), int(resolved_height or 1080), int(resolved_duration)


def _write_private_files(
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
    meta = {"draft_name": draft_name, "draft_root_path": str(draft_path), "tm_duration": duration_us}
    (draft_path / "draft_content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    (draft_path / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
