"""Workflow orchestration for scanning and creating JianYing drafts."""

from __future__ import annotations

from pathlib import Path

from .cache_extractor import find_combination_mp4s
from .draft_detector import detect_recent_drafts
from .draft_creator import create_extracted_draft
from .env import JianYingEnv
from .media_validator import validate_media_file
from .models import (
    CacheOrigin,
    CandidateStatus,
    CreateDraftRequest,
    CreateDraftResult,
    MediaCandidate,
    ResolvedSource,
    SourceMode,
    WorkflowError,
)
from .private_cache_draft import create_private_cache_draft
from .private_cache_scan import inspect_private_cache


def scan_source(
    mode: SourceMode,
    *,
    project_path: str | Path | None = None,
    mp4_path: str | Path | None = None,
    env: JianYingEnv | None = None,
) -> ResolvedSource:
    env = env or JianYingEnv()
    if mode == SourceMode.AUTO:
        projects = detect_recent_drafts(env.info.draft_dir)
        if not projects:
            raise WorkflowError("no_recent_project", "没有找到最近项目。")
        return scan_source(SourceMode.PROJECT, project_path=projects[0].path, env=env)
    if mode == SourceMode.PROJECT:
        if project_path is None:
            raise WorkflowError("project_required", "缺少项目路径。")
        project = Path(project_path)
        files = find_combination_mp4s(project, require_video=False, recent_seconds=None)
        candidates = [
            MediaCandidate(path=file.path, status=CandidateStatus.AVAILABLE, origin=CacheOrigin.PROJECT, size_bytes=file.size_bytes)
            for file in files
        ]
        return ResolvedSource(project.name, candidates, SourceMode.PROJECT, candidates)
    if mode == SourceMode.MP4:
        if mp4_path is None:
            raise WorkflowError("mp4_required", "缺少 MP4 路径。")
        path = Path(mp4_path)
        validation = validate_media_file(path)
        candidate = MediaCandidate(
            path=path,
            status=validation.status,
            origin=CacheOrigin.MANUAL_FILE,
            size_bytes=validation.size_bytes,
            width=validation.width,
            height=validation.height,
            duration_ms=validation.duration_ms,
            rejection_reason=validation.reason,
        )
        available = [candidate] if validation.status == CandidateStatus.AVAILABLE else []
        return ResolvedSource(path.stem, [candidate], SourceMode.MP4, available)
    raise WorkflowError("unsupported_mode", f"不支持的模式: {mode}")


def create_draft_from_source(request: CreateDraftRequest, *, env: JianYingEnv | None = None) -> CreateDraftResult:
    env = env or JianYingEnv()
    source = scan_source(request.mode, project_path=request.project_path, mp4_path=request.mp4_path, env=env)
    selected = _select_candidate(source, request.selected_media_path)
    if selected is None:
        raise WorkflowError("no_media", "没有可用媒体。")

    private = inspect_private_cache(selected.path)
    if private.status == "private_importable":
        created = create_private_cache_draft(env.info.draft_dir, selected.path, request.draft_name or source.source_name)
    else:
        created = create_extracted_draft(env.info.draft_dir, selected.path, request.draft_name or source.source_name)
    return CreateDraftResult(status="success", selected_media=selected, created_draft=created, tracked_mp4=selected.path)


def _select_candidate(source: ResolvedSource, selected_media_path: Path | None) -> MediaCandidate | None:
    if selected_media_path is not None:
        for candidate in source.candidates:
            if candidate.path == selected_media_path:
                return candidate
    if source.available_candidates:
        return source.available_candidates[0]
    return source.candidates[0] if source.candidates else None
