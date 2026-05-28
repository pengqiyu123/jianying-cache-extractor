"""Locate JianYing pre-rendered combination cache files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time

from .media_validator import inspect_video


RECENT_CACHE_WINDOW_SECONDS = 30 * 60


@dataclass(frozen=True)
class CacheFile:
    path: Path
    size_bytes: int
    modified_at: datetime
    width: int | None = None
    height: int | None = None
    duration_ms: float | None = None


def find_combination_mp4s(
    project_path: str | Path,
    *,
    require_video: bool = True,
    recent_seconds: int | None = RECENT_CACHE_WINDOW_SECONDS,
) -> list[CacheFile]:
    """Return combination MP4 caches sorted newest first.

    JianYing stores pre-rendered compound clip output under
    ``Resources/combination``. Transparent-channel sidecars named
    ``*.alpha.mp4`` are intentionally skipped.

    By default the result only includes files with a readable visual track.
    JianYing v10.6 may leave large ``.mp4`` cache blobs that are not standard
    MP4 containers, so size alone is not enough to prove importability.
    """
    project = Path(project_path)
    combination_dir = project / "Resources" / "combination"
    if not combination_dir.is_dir():
        return []

    files: list[CacheFile] = []
    min_mtime = time.time() - recent_seconds if recent_seconds is not None else None
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
        video_info = inspect_video(path)
        if require_video and video_info is None:
            continue
        width, height, duration_ms = video_info if video_info is not None else (None, None, None)
        files.append(
            CacheFile(
                path=path,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                width=width,
                height=height,
                duration_ms=duration_ms,
            )
        )

    return sorted(files, key=lambda item: item.modified_at, reverse=True)
