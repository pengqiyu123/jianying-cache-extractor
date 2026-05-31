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


@dataclass(frozen=True)
class CopyVerification:
    source_path: Path
    target_path: Path
    source_size: int
    target_size: int
    size_verified: bool


def inspect_video(path: str | Path) -> VideoInfo | tuple[int | None, int | None, float | None] | None:
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


def validate_video(path: str | Path) -> VideoInfo | tuple[int | None, int | None, float | None] | None:
    return inspect_video(path)


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


def wait_until_stable(path: str | Path, *, samples: int = 3, interval_seconds: float = 0.5) -> bool:
    media_path = Path(path)
    if samples < 2:
        samples = 2
    last: tuple[int, float] | None = None
    for index in range(samples):
        try:
            stat = media_path.stat()
        except OSError:
            return False
        current = (stat.st_size, stat.st_mtime)
        if last is not None and current != last:
            return False
        last = current
        if index < samples - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)
    return True


def verify_copy(source: str | Path, target: str | Path) -> CopyVerification:
    source_path = Path(source)
    target_path = Path(target)
    try:
        source_size = source_path.stat().st_size
    except OSError:
        source_size = -1
    try:
        target_size = target_path.stat().st_size
    except OSError:
        target_size = -1
    return CopyVerification(
        source_path=source_path,
        target_path=target_path,
        source_size=source_size,
        target_size=target_size,
        size_verified=source_size >= 0 and source_size == target_size,
    )


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

    if require_stable and not wait_until_stable(media_path):
        return MediaValidationResult(
            status=CandidateStatus.WRITING,
            reason="still_writing",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    info = inspect_video(media_path)
    if info is None:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="no_video_track",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    width, height, duration_ms = _shape(info)
    if not width or not height:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="invalid_dimensions",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )
    if not duration_ms or duration_ms <= 0:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="invalid_duration",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    return MediaValidationResult(
        status=CandidateStatus.AVAILABLE,
        width=width,
        height=height,
        duration_ms=duration_ms,
        size_bytes=stat.st_size,
        modified_at=modified_at,
    )


def _shape(info) -> tuple[int | None, int | None, float | None]:
    if isinstance(info, tuple):
        return info[0], info[1], info[2]
    return getattr(info, "width", None), getattr(info, "height", None), getattr(info, "duration_ms", None)
