"""Shared data models for the JianYing cache extraction workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class SourceMode(str, Enum):
    AUTO = "auto"
    PROJECT = "project"
    MP4 = "mp4"


class CandidateStatus(str, Enum):
    AVAILABLE = "available"
    WRITING = "writing"
    REJECTED = "rejected"


class CacheOrigin(str, Enum):
    PROJECT = "project"
    CLOUD_CACHE = "cloud_cache"
    MANUAL_FILE = "manual_file"


class ProcessStatus(str, Enum):
    NOT_INSTALLED = "not_installed"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    BACKGROUND = "background"
    TRAY_ONLY = "tray_only"


class PrivateCacheStatus(str, Enum):
    STANDARD_IMPORTABLE = "standard_importable"
    PRIVATE_IMPORTABLE = "private_importable"
    PRIVATE_NOT_IMPORTABLE = "private_not_importable"


class WorkflowPhase(str, Enum):
    IDLE = "idle"
    COMPOSITE_DONE = "composite_done"
    RESTARTED = "restarted"
    IMPORTED = "imported"


@dataclass(frozen=True)
class MediaCandidate:
    path: Path
    origin: CacheOrigin = CacheOrigin.PROJECT
    source_project_name: str | None = None
    size_bytes: int = 0
    modified_at: datetime = field(default_factory=lambda: datetime.fromtimestamp(0))
    width: int | None = None
    height: int | None = None
    duration_ms: float | None = None
    status: CandidateStatus = CandidateStatus.REJECTED
    score: int = 0
    rejection_reason: str | None = None
    private_status: PrivateCacheStatus | None = None


@dataclass(frozen=True)
class JianYingInfo:
    install_dir: Path
    exe_path: Path
    launcher_path: Path
    draft_dir: Path
    version: str | None = None


@dataclass(frozen=True)
class DraftFolder:
    path: Path
    name: str
    modified_at: datetime
    has_combination_cache: bool = False


@dataclass(frozen=True)
class CacheFile:
    path: Path
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True)
class CompoundResult:
    status: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportResult:
    status: str
    error_detail: str | None = None


@dataclass(frozen=True)
class CreatedDraft:
    draft_path: Path
    name: str | None = None
    media_path: Path | None = None
    source_media_path: Path | None = None
    size_verified: bool = False
    sha256: str | None = None
    draft_name: str | None = None

    def __post_init__(self) -> None:
        resolved = self.name or self.draft_name or self.draft_path.name
        object.__setattr__(self, "name", resolved)
        object.__setattr__(self, "draft_name", resolved)


@dataclass(frozen=True)
class CreateDraftResult:
    status: str
    mode: SourceMode | None = None
    selected_media: MediaCandidate | None = None
    created_draft: CreatedDraft | None = None
    warnings: list[str] = field(default_factory=list)
    tracked_mp4: Path | None = None


@dataclass(frozen=True)
class ResolvedSource:
    source_name: str
    candidates: list[MediaCandidate]
    mode: SourceMode
    project_path: Path | None = None
    available_candidates: list[MediaCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.available_candidates:
            object.__setattr__(
                self,
                "available_candidates",
                [candidate for candidate in self.candidates if candidate.status == CandidateStatus.AVAILABLE],
            )


@dataclass(frozen=True)
class CreateDraftRequest:
    mode: SourceMode
    project_path: Path | None = None
    mp4_path: Path | None = None
    source_name: str | None = None
    selected_media_path: Path | None = None
    draft_name: str | None = None
    fps: int = 30
    require_confirmed_candidate: bool = True


class WorkflowError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
