"""High-level workflow shared by CLI and GUI."""

from __future__ import annotations

from pathlib import Path

from .draft_creator import create_extracted_draft
from .env import JianYingEnv
from .models import (
    CandidateStatus,
    CreateDraftRequest,
    CreateDraftResult,
    MediaCandidate,
    ResolvedSource,
    SourceMode,
    WorkflowError,
)
from .source_resolver import resolve_auto, resolve_mp4, resolve_project


def scan_source(
    request: CreateDraftRequest,
    *,
    draft_root: str | Path | None = None,
    env: JianYingEnv | None = None,
    process=None,
) -> ResolvedSource:
    """Resolve candidates for a workflow request."""
    if request.mode == SourceMode.AUTO:
        return resolve_auto(draft_root=draft_root, env=env, process=process)
    if request.mode == SourceMode.PROJECT:
        if request.project_path is None:
            raise WorkflowError("project_required", "请选择剪映项目目录")
        return resolve_project(request.project_path, draft_root=draft_root)
    if request.mode == SourceMode.MP4:
        if request.mp4_path is None:
            raise WorkflowError("mp4_required", "请选择 MP4 文件")
        return resolve_mp4(request.mp4_path, source_name=request.source_name)
    raise WorkflowError("unsupported_mode", f"不支持的来源模式: {request.mode}")


def create_draft_from_source(
    request: CreateDraftRequest,
    *,
    draft_root: str | Path | None = None,
    env: JianYingEnv | None = None,
    process=None,
) -> CreateDraftResult:
    """Create a new JianYing draft from a resolved media source."""
    env = env or JianYingEnv()
    root = Path(draft_root) if draft_root is not None else env.info.draft_dir
    source = scan_source(request, draft_root=root, env=env, process=process)
    selected = _select_candidate(source, request.selected_media_path)
    if selected is None:
        raise WorkflowError("no_valid_media", "未找到可导入的视频缓存")

    created = create_extracted_draft(root, selected.path, request.source_name or source.source_name, fps=request.fps)
    return CreateDraftResult(
        status="draft_created",
        mode=request.mode,
        selected_media=selected,
        created_draft=created,
        warnings=source.warnings or [],
    )


def _select_candidate(source: ResolvedSource, selected_media_path: Path | None) -> MediaCandidate | None:
    available = [candidate for candidate in source.candidates if candidate.status == CandidateStatus.AVAILABLE]
    if selected_media_path is not None:
        selected = Path(selected_media_path)
        return next((candidate for candidate in available if candidate.path == selected), None)
    if not available:
        return None
    return sorted(available, key=lambda candidate: (candidate.score, candidate.modified_at), reverse=True)[0]
