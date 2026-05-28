"""Resolve automatic, project, and manual MP4 sources into candidates."""

from __future__ import annotations

from pathlib import Path

from .env import JianYingEnv
from .media_validator import validate_media_file
from .models import (
    CacheOrigin,
    CandidateStatus,
    MediaCandidate,
    ResolvedSource,
    SourceMode,
    WorkflowError,
)
from .project_detector import detect_active_project


def resolve_auto(
    *,
    draft_root: str | Path | None = None,
    env: JianYingEnv | None = None,
    process=None,
) -> ResolvedSource:
    """Resolve the currently active project, requiring JianYing to be running."""
    env = env or JianYingEnv()
    root = Path(draft_root) if draft_root is not None else env.info.draft_dir
    project = detect_active_project(root, process=process)
    if project is None:
        raise WorkflowError("no_active_project", "没有找到最近活跃的剪映项目")
    return resolve_project(project.path, draft_root=root)


def resolve_project(project_path: str | Path, *, draft_root: str | Path | None = None) -> ResolvedSource:
    """Resolve candidates from a project and all matching cloud_cache mirrors."""
    project = Path(project_path)
    if not project.is_dir():
        raise WorkflowError("project_not_found", f"项目目录不存在: {project}")

    root = Path(draft_root) if draft_root is not None else project.parent
    candidates = _scan_project(project, CacheOrigin.PROJECT, project.name)

    if root.is_dir():
        for mirror_root in sorted(root.iterdir(), key=lambda item: item.name):
            if not mirror_root.is_dir() or not mirror_root.name.startswith(".cloud_cache_"):
                continue
            mirror_project = mirror_root / project.name
            if mirror_project.is_dir():
                candidates.extend(_scan_project(mirror_project, CacheOrigin.CLOUD_CACHE, project.name))

    return ResolvedSource(
        mode=SourceMode.PROJECT,
        source_name=project.name,
        project_path=project,
        candidates=_sort_candidates(candidates),
        warnings=[],
    )


def resolve_mp4(mp4_path: str | Path, *, source_name: str | None = None) -> ResolvedSource:
    """Resolve a manually selected MP4 into a single candidate."""
    media_path = Path(mp4_path)
    validation = validate_media_file(media_path)
    if validation.reason == "media_not_found":
        raise WorkflowError("media_not_found", f"媒体文件不存在: {media_path}")
    candidate = _candidate_from_validation(
        media_path,
        CacheOrigin.MANUAL_FILE,
        source_name or media_path.stem,
        validation,
        base_score=100,
    )
    return ResolvedSource(
        mode=SourceMode.MP4,
        source_name=source_name or media_path.stem,
        project_path=None,
        candidates=[candidate],
        warnings=[],
    )


def _scan_project(project: Path, origin: CacheOrigin, source_project_name: str) -> list[MediaCandidate]:
    combination_dir = project / "Resources" / "combination"
    if not combination_dir.is_dir():
        return []

    candidates: list[MediaCandidate] = []
    for media_path in combination_dir.glob("*.mp4"):
        validation = validate_media_file(media_path)
        candidates.append(
            _candidate_from_validation(
                media_path,
                origin,
                source_project_name,
                validation,
                base_score=80 if origin == CacheOrigin.CLOUD_CACHE else 70,
            )
        )
    return candidates


def _candidate_from_validation(
    path: Path,
    origin: CacheOrigin,
    source_project_name: str | None,
    validation,
    *,
    base_score: int,
) -> MediaCandidate:
    modified_at = validation.modified_at
    size_bytes = validation.size_bytes
    if modified_at is None or size_bytes == 0:
        try:
            stat = path.stat()
        except OSError:
            pass
        else:
            modified_at = modified_at or __import__("datetime").datetime.fromtimestamp(stat.st_mtime)
            size_bytes = size_bytes or stat.st_size
    if modified_at is None:
        modified_at = __import__("datetime").datetime.fromtimestamp(0)

    score = base_score if validation.status == CandidateStatus.AVAILABLE else 0
    if validation.status == CandidateStatus.AVAILABLE:
        score += min(size_bytes // (1024 * 1024), 50)

    return MediaCandidate(
        path=path,
        origin=origin,
        source_project_name=source_project_name,
        size_bytes=size_bytes,
        modified_at=modified_at,
        width=validation.width,
        height=validation.height,
        duration_ms=validation.duration_ms,
        status=validation.status,
        score=int(score),
        rejection_reason=validation.reason,
    )


def _sort_candidates(candidates: list[MediaCandidate]) -> list[MediaCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.status == CandidateStatus.AVAILABLE,
            candidate.score,
            candidate.modified_at,
        ),
        reverse=True,
    )
