"""Detect recently modified JianYing draft projects."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .models import DraftFolder


def detect_recent_drafts(draft_root: str | Path, recent_minutes: int = 30) -> list[DraftFolder]:
    root = Path(draft_root)
    if not root.is_dir():
        return []

    cutoff = datetime.now() - timedelta(minutes=recent_minutes)
    drafts: list[DraftFolder] = []
    for path in root.iterdir():
        if not path.is_dir() or path.name.startswith("."):
            continue
        modified_at = _project_modified_at(path)
        if modified_at < cutoff:
            continue
        drafts.append(
            DraftFolder(
                path=path,
                name=path.name,
                modified_at=modified_at,
                has_combination_cache=(path / "Resources" / "combination").is_dir(),
            )
        )
    return sorted(drafts, key=lambda draft: draft.modified_at, reverse=True)


def detect_active_project(draft_root: str | Path) -> DraftFolder | None:
    drafts = detect_recent_drafts(draft_root)
    with_cache = [draft for draft in drafts if draft.has_combination_cache]
    return (with_cache or drafts)[0] if drafts else None


def _project_modified_at(path: Path) -> datetime:
    stat = path.stat()
    return datetime.fromtimestamp(max(stat.st_mtime, stat.st_ctime))
