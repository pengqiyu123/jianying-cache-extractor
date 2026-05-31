"""Workflow orchestration for scanning and creating JianYing drafts."""

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
from .private_cache_draft import create_private_cache_draft
from .private_cache_scan import inspect_private_cache
from .source_resolver import resolve_auto, resolve_mp4, resolve_project


def scan_source(
    mode: SourceMode,
    *,
    project_path: str | Path | None = None,
    mp4_path: str | Path | None = None,
    source_name: str | None = None,
    env: JianYingEnv | None = None,
    draft_root: str | Path | None = None,
    process=None,
) -> ResolvedSource:
    env = env or JianYingEnv()
    root = Path(draft_root) if draft_root is not None else None
    if mode == SourceMode.AUTO:
        return resolve_auto(draft_root=root, env=env, process=process)
    if mode == SourceMode.PROJECT:
        if project_path is None:
            raise WorkflowError("project_required", "缺少项目路径。")
        return resolve_project(project_path, draft_root=root)
    if mode == SourceMode.MP4:
        if mp4_path is None:
            raise WorkflowError("mp4_required", "缺少 MP4 路径。")
        return resolve_mp4(mp4_path, source_name=source_name)
    raise WorkflowError("unsupported_mode", f"不支持的模式: {mode}")


def create_draft_from_source(
    request: CreateDraftRequest,
    *,
    env: JianYingEnv | None = None,
    draft_root: str | Path | None = None,
) -> CreateDraftResult:
    env = env or JianYingEnv()
    root = Path(draft_root) if draft_root is not None else env.info.draft_dir
    source = scan_source(
        request.mode,
        project_path=request.project_path,
        mp4_path=request.mp4_path,
        source_name=request.source_name,
        env=env,
        draft_root=root,
    )
    selected = _select_candidate(source, request.selected_media_path)
    if selected is None or selected.status != CandidateStatus.AVAILABLE:
        raise WorkflowError("no_valid_media", "未找到可导入的视频缓存")

    private = inspect_private_cache(selected.path)
    if private.status == "private_importable":
        created = create_private_cache_draft(root, selected.path, request.draft_name or source.source_name)
    else:
        created = create_extracted_draft(root, selected.path, request.draft_name or source.source_name, fps=request.fps)
    return CreateDraftResult(
        status="draft_created",
        mode=request.mode,
        selected_media=selected,
        created_draft=created,
        tracked_mp4=selected.path,
    )


def _select_candidate(source: ResolvedSource, selected_media_path: Path | None) -> MediaCandidate | None:
    if selected_media_path is not None:
        for candidate in source.candidates:
            if candidate.path == selected_media_path:
                return candidate
    if source.available_candidates:
        return source.available_candidates[0]
    return source.candidates[0] if source.candidates else None
