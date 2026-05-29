"""Detect the most recently active JianYing draft project."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .cache_extractor import CacheFile, find_combination_mp4s
from .process import JianYingProcess, ProcessStatus


WATCHED_FILES = ("draft_content.json", "draft_content.json.bak", "draft.extra")


class ProcessLike(Protocol):
    def status(self) -> ProcessStatus:
        ...


@dataclass(frozen=True)
class ActiveProject:
    name: str
    path: Path
    combination_dir: Path
    latest_mp4: Path | None
    last_modified: datetime
    caches: list[CacheFile]


def project_last_modified(project_path: str | Path) -> datetime | None:
    """Return newest mtime from core JianYing draft files."""
    project = Path(project_path)
    mtimes: list[float] = []
    for filename in WATCHED_FILES:
        path = project / filename
        if path.exists():
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes))


def detect_active_project(
    draft_dir: str | Path,
    process: ProcessLike | None = None,
) -> ActiveProject | None:
    """Find the newest active project with combination cache files.

    A project is considered actionable only when JianYing is running and the
    project has at least one non-empty combination MP4.
    """
    process = process or JianYingProcess()
    if process.status() != ProcessStatus.RUNNING:
        return None

    root = Path(draft_dir)
    if not root.is_dir():
        return None

    cache_mirrors = [item for item in root.iterdir() if item.is_dir() and item.name.startswith(".cloud_cache_")]

    candidates: list[ActiveProject] = []
    for project in root.iterdir():
        if not project.is_dir():
            continue
        if project.name.startswith("."):
            continue
        caches = find_combination_mp4s(project)
        cache_source_dir = project
        if not caches:
            for mirror_root in cache_mirrors:
                mirror_project = mirror_root / project.name
                caches = find_combination_mp4s(mirror_project)
                if caches:
                    cache_source_dir = mirror_project
                    break
        if not caches:
            caches = find_combination_mp4s(project, require_video=False)
            cache_source_dir = project
        if not caches:
            for mirror_root in cache_mirrors:
                mirror_project = mirror_root / project.name
                caches = find_combination_mp4s(mirror_project, require_video=False)
                if caches:
                    cache_source_dir = mirror_project
                    break
        if not caches:
            continue
        last_modified = project_last_modified(project)
        if last_modified is None:
            try:
                last_modified = datetime.fromtimestamp(project.stat().st_mtime)
            except OSError:
                continue
        candidates.append(
            ActiveProject(
                name=project.name,
                path=project,
                combination_dir=cache_source_dir / "Resources" / "combination",
                latest_mp4=caches[0].path,
                last_modified=last_modified,
                caches=caches,
            )
        )

    if not candidates:
        return None

    return max(candidates, key=lambda item: item.last_modified)
