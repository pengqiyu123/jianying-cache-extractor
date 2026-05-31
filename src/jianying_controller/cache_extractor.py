"""Locate JianYing pre-rendered combination cache files."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .media_validator import validate_video
from .models import CacheFile


RECENT_CACHE_WINDOW_SECONDS = 30 * 60


def find_combination_mp4s(
    project_path: str | Path,
    *,
    require_video: bool = True,
    recent_seconds: int | None = RECENT_CACHE_WINDOW_SECONDS,
) -> list[CacheFile]:
    combination_dir = Path(project_path) / "Resources" / "combination"
    if not combination_dir.is_dir():
        return []

    min_mtime = time.time() - recent_seconds if recent_seconds is not None else None
    files: list[CacheFile] = []
    for path in combination_dir.glob("*.mp4"):
        if path.name.lower().endswith(".alpha.mp4"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        if min_mtime is not None and stat.st_mtime < min_mtime:
            continue
        video = validate_video(path)
        if require_video and video is None:
            continue
        files.append(
            CacheFile(
                path=path,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )

    return sorted(files, key=lambda file: file.modified_at, reverse=True)


def scan_latest_cache(project_path: str | Path, *, require_video: bool = False) -> Path | None:
    files = find_combination_mp4s(project_path, require_video=require_video, recent_seconds=None)
    return files[0].path if files else None
