"""Media validation helpers for JianYing cache files."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pymediainfo import MediaInfo

from .models import CandidateStatus


@dataclass(frozen=True)
class VideoInfo:
    width: int | None
    height: int | None
    duration_ms: float | None


@dataclass(frozen=True)
class MediaValidationResult:
    status: CandidateStatus
    reason: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: float | None = None
    size_bytes: int = 0
    modified_at: datetime | None = None


def validate_video(path: str | Path) -> VideoInfo | None:
    """Return video metadata when MediaInfo can parse a visual track."""
    try:
        info = MediaInfo.parse(str(path), mediainfo_options={"File_TestContinuousFileNames": "0"})
    except Exception:
        return None

    tracks = list(info.video_tracks) or list(info.image_tracks)
    if not tracks:
        return None
    track = tracks[0]
    return VideoInfo(
        width=getattr(track, "width", None),
        height=getattr(track, "height", None),
        duration_ms=getattr(track, "duration", None),
    )


def is_file_stable(path: str | Path, *, interval: float = 1.0) -> bool:
    media_path = Path(path)
    try:
        first = media_path.stat().st_size
    except OSError:
        return False
    if interval > 0:
        time.sleep(interval)
    try:
        second = media_path.stat().st_size
    except OSError:
        return False
    return first == second


def validate_media_file(path: str | Path, *, require_stable: bool = False) -> MediaValidationResult:
    media_path = Path(path)
    if not media_path.exists():
        return MediaValidationResult(status=CandidateStatus.REJECTED, reason="media_not_found")
    if not media_path.is_file():
        return MediaValidationResult(status=CandidateStatus.REJECTED, reason="not_file")
    if media_path.suffix.lower() != ".mp4":
        return MediaValidationResult(status=CandidateStatus.REJECTED, reason="not_mp4")
    if media_path.name.lower().endswith(".alpha.mp4"):
        return MediaValidationResult(status=CandidateStatus.REJECTED, reason="alpha_sidecar")

    try:
        stat = media_path.stat()
    except OSError:
        return MediaValidationResult(status=CandidateStatus.REJECTED, reason="read_failed")

    modified_at = datetime.fromtimestamp(stat.st_mtime)
    if stat.st_size <= 0:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="empty_file",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    if require_stable and not is_file_stable(media_path):
        return MediaValidationResult(
            status=CandidateStatus.WRITING,
            reason="still_writing",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    info = validate_video(media_path)
    if info is None:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="no_video_track",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    return MediaValidationResult(
        status=CandidateStatus.AVAILABLE,
        width=info.width,
        height=info.height,
        duration_ms=info.duration_ms,
        size_bytes=stat.st_size,
        modified_at=modified_at,
    )
