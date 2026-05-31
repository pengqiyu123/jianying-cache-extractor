"""Classify JianYing private combination cache files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .media_validator import validate_video
from .models import PrivateCacheStatus


@dataclass(frozen=True)
class PrivateCacheInspection:
    status: str
    reason: str | None
    width: int | None
    height: int | None
    duration_ms: float | None
    size_bytes: int
    modified_at: datetime | None


def inspect_private_cache(path: str | Path) -> PrivateCacheInspection:
    source = Path(path)
    if not source.exists():
        return _result(PrivateCacheStatus.PRIVATE_NOT_IMPORTABLE.value, "media_not_found", source)
    if not source.is_file():
        return _result(PrivateCacheStatus.PRIVATE_NOT_IMPORTABLE.value, "not_file", source)
    if source.suffix.lower() != ".mp4" or source.name.lower().endswith(".alpha.mp4"):
        return _result(PrivateCacheStatus.PRIVATE_NOT_IMPORTABLE.value, "not_main_mp4", source)
    if source.stat().st_size <= 0:
        return _result(PrivateCacheStatus.PRIVATE_NOT_IMPORTABLE.value, "empty_file", source)

    standard = validate_video(source)
    standard_width, standard_height, standard_duration = _shape(standard)
    if standard is not None and standard_width and standard_height:
        return _result(
            PrivateCacheStatus.STANDARD_IMPORTABLE.value,
            None,
            source,
            width=standard_width,
            height=standard_height,
            duration_ms=standard_duration,
        )

    sidecar = source.with_name(f"{source.name}.alpha.mp4")
    if not sidecar.is_file() or sidecar.stat().st_size <= 0:
        return _result(PrivateCacheStatus.PRIVATE_NOT_IMPORTABLE.value, "missing_alpha_sidecar", source)
    alpha_info = validate_video(sidecar)
    alpha_width, alpha_height, alpha_duration = _shape(alpha_info)
    if alpha_info is None or not alpha_width or not alpha_height:
        return _result(PrivateCacheStatus.PRIVATE_NOT_IMPORTABLE.value, "alpha_unreadable", source)
    return _result(
        PrivateCacheStatus.PRIVATE_IMPORTABLE.value,
        None,
        source,
        width=alpha_width,
        height=alpha_height,
        duration_ms=alpha_duration,
    )


def _result(
    status: str,
    reason: str | None,
    source: Path,
    *,
    width: int | None = None,
    height: int | None = None,
    duration_ms: float | None = None,
) -> PrivateCacheInspection:
    try:
        stat = source.stat()
        return PrivateCacheInspection(
            status=status,
            reason=reason,
            width=width,
            height=height,
            duration_ms=duration_ms,
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )
    except OSError:
        return PrivateCacheInspection(status, reason, width, height, duration_ms, 0, None)


def _shape(info) -> tuple[int | None, int | None, float | None]:
    if info is None:
        return None, None, None
    if isinstance(info, tuple):
        return info[0], info[1], info[2]
    return getattr(info, "width", None), getattr(info, "height", None), getattr(info, "duration_ms", None)
