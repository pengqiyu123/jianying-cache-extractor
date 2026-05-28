import os
from pathlib import Path

import pytest

from jianying_controller.models import (
    CacheOrigin,
    CandidateStatus,
    CreateDraftRequest,
    CreatedDraft,
    MediaCandidate,
    SourceMode,
    WorkflowError,
)
from jianying_controller.workflow import create_draft_from_source


def touch(path: Path, content: bytes = b"x", mtime: int = 1_700_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))


def test_create_draft_from_mp4_returns_structured_result(tmp_path, monkeypatch):
    media = tmp_path / "manual.mp4"
    touch(media, b"mp4")
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()

    monkeypatch.setattr(
        "jianying_controller.media_validator.inspect_video",
        lambda path: (1280, 720, 5000.0),
    )

    created = CreatedDraft(
        name="提取_手动素材_20260528_210210",
        draft_path=draft_root / "提取_手动素材_20260528_210210",
        media_path=draft_root / "提取_手动素材_20260528_210210" / "Resources" / "extracted" / media.name,
        source_media_path=media,
        size_verified=True,
    )
    monkeypatch.setattr(
        "jianying_controller.workflow.create_extracted_draft",
        lambda draft_dir, mp4_path, source_name, fps=30: created,
    )

    result = create_draft_from_source(
        CreateDraftRequest(mode=SourceMode.MP4, mp4_path=media, source_name="手动素材"),
        draft_root=draft_root,
    )

    assert result.status == "draft_created"
    assert result.mode == SourceMode.MP4
    assert result.selected_media is not None
    assert result.selected_media.path == media
    assert result.created_draft == created


def test_create_draft_from_source_requires_available_candidate(tmp_path):
    media = tmp_path / "bad.mp4"
    touch(media, b"not mp4")

    with pytest.raises(WorkflowError) as exc:
        create_draft_from_source(
            CreateDraftRequest(mode=SourceMode.MP4, mp4_path=media, source_name="bad"),
            draft_root=tmp_path,
        )

    assert exc.value.code == "no_valid_media"
