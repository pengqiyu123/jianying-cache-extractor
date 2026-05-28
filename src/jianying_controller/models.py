"""Shared data models for JianYing cache extraction workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class SourceMode(str, Enum):
    AUTO = "auto"
    PROJECT = "project"
    MP4 = "mp4"


class CacheOrigin(str, Enum):
    PROJECT = "project"
    CLOUD_CACHE = "cloud_cache"
    MANUAL_FILE = "manual_file"


class CandidateStatus(str, Enum):
    AVAILABLE = "available"
    WRITING = "writing"
    REJECTED = "rejected"


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
    source_size_bytes: int
    target_size_bytes: int
    size_verified: bool
    sha256: str | None = None


@dataclass(frozen=True)
class MediaCandidate:
    path: Path
    origin: CacheOrigin
    source_project_name: str | None
    size_bytes: int
    modified_at: datetime
    width: int | None
    height: int | None
    duration_ms: float | None
    status: CandidateStatus
    score: int = 0
    rejection_reason: str | None = None


@dataclass(frozen=True)
class ResolvedSource:
    mode: SourceMode
    source_name: str
    candidates: list[MediaCandidate]
    project_path: Path | None = None
    warnings: list[str] | None = None

    @property
    def available_candidates(self) -> list[MediaCandidate]:
        return [candidate for candidate in self.candidates if candidate.status == CandidateStatus.AVAILABLE]


@dataclass(frozen=True)
class CreateDraftRequest:
    mode: SourceMode
    project_path: Path | None = None
    mp4_path: Path | None = None
    source_name: str | None = None
    selected_media_path: Path | None = None
    fps: int = 30
    require_confirmed_candidate: bool = True


@dataclass(frozen=True)
class CreatedDraft:
    name: str
    draft_path: Path
    media_path: Path
    source_media_path: Path
    size_verified: bool = True
    sha256: str | None = None


@dataclass(frozen=True)
class CreateDraftResult:
    status: str
    mode: SourceMode
    selected_media: MediaCandidate | None
    created_draft: CreatedDraft | None
    warnings: list[str]


class WorkflowError(Exception):
    """Structured error for CLI/GUI workflow boundaries."""

    def __init__(self, code: str, message: str, details: list[Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "failed",
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
