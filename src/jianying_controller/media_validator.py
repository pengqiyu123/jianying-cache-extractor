"""Media validation and copy checks for JianYing cache files."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path

from pymediainfo import MediaInfo

from .models import CandidateStatus, CopyVerification, MediaValidationResult


MIN_MEDIA_BYTES = 1


def inspect_video(path: str | Path) -> tuple[int | None, int | None, float | None] | None:
    """Return basic visual-track information for an importable media file."""
    try:
        info = MediaInfo.parse(
            str(path),
            mediainfo_options={"File_TestContinuousFileNames": "0"},
        )
    except Exception:
        return None

    tracks = list(info.video_tracks) or list(info.image_tracks)
    if not tracks:
        return None
    track = tracks[0]
    return (
        getattr(track, "width", None),
        getattr(track, "height", None),
        getattr(track, "duration", None),
    )


def validate_media_file(path: str | Path, *, require_stable: bool = False) -> MediaValidationResult:
    """Validate whether a path is an MP4 that JianYing can import."""
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
    if stat.st_size < MIN_MEDIA_BYTES:
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

    video_info = inspect_video(media_path)
    if video_info is None:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="no_video_track",
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )

    width, height, duration_ms = video_info
    if not width or not height:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="invalid_dimensions",
            width=width,
            height=height,
            duration_ms=duration_ms,
            size_bytes=stat.st_size,
            modified_at=modified_at,
        )
    if not duration_ms or duration_ms <= 0:
        return MediaValidationResult(
            status=CandidateStatus.REJECTED,
            reason="invalid_duration",
            width=width,
            height=height,
            duration_ms=duration_ms,
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


def wait_until_stable(path: str | Path, *, samples: int = 3, interval_seconds: float = 0.2) -> bool:
    """Return True when size and mtime remain unchanged across samples."""
    media_path = Path(path)
    snapshots: list[tuple[int, int]] = []
    for index in range(max(1, samples)):
        try:
            stat = media_path.stat()
        except OSError:
            return False
        snapshots.append((stat.st_size, stat.st_mtime_ns))
        if index < samples - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)
    return len(set(snapshots)) == 1


def verify_copy(source: str | Path, target: str | Path, *, compute_hash: bool = False) -> CopyVerification:
    """Verify that a copied media file matches the source size, optionally hash."""
    source_path = Path(source)
    target_path = Path(target)
    source_size = source_path.stat().st_size if source_path.exists() else -1
    target_size = target_path.stat().st_size if target_path.exists() else -1
    sha256 = _sha256(target_path) if compute_hash and target_path.exists() else None
    return CopyVerification(
        source_path=source_path,
        target_path=target_path,
        source_size_bytes=source_size,
        target_size_bytes=target_size,
        size_verified=source_size == target_size and source_size >= 0,
        sha256=sha256,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
