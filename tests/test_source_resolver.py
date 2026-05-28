import os
from pathlib import Path

from jianying_controller.models import CacheOrigin, CandidateStatus, SourceMode
from jianying_controller.source_resolver import resolve_mp4, resolve_project


def touch(path: Path, content: bytes = b"x", mtime: int = 1_700_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))


def test_resolve_project_scans_cloud_cache_without_requiring_jianying_running(tmp_path, monkeypatch):
    project = tmp_path / "项目A"
    touch(project / "draft_content.json", b"encrypted", 900)
    touch(project / "Resources" / "combination" / "broken_video.mp4", b"blob", 800)
    valid = (
        tmp_path
        / ".cloud_cache_123"
        / project.name
        / "Resources"
        / "combination"
        / "valid_video.mp4"
    )
    touch(valid, b"mp4", 700)

    monkeypatch.setattr(
        "jianying_controller.media_validator.inspect_video",
        lambda path: (1920, 1080, 1000.0) if Path(path).name == "valid_video.mp4" else None,
    )

    source = resolve_project(project, draft_root=tmp_path)

    assert source.mode == SourceMode.PROJECT
    assert source.source_name == project.name
    assert [candidate.path for candidate in source.available_candidates] == [valid]
    assert source.available_candidates[0].origin == CacheOrigin.CLOUD_CACHE


def test_resolve_mp4_builds_manual_candidate(tmp_path, monkeypatch):
    media = tmp_path / "manual.mp4"
    touch(media, b"mp4")
    monkeypatch.setattr(
        "jianying_controller.media_validator.inspect_video",
        lambda path: (1280, 720, 5000.0),
    )

    source = resolve_mp4(media, source_name="手动素材")

    assert source.mode == SourceMode.MP4
    assert source.source_name == "手动素材"
    assert source.candidates[0].origin == CacheOrigin.MANUAL_FILE
    assert source.candidates[0].status == CandidateStatus.AVAILABLE
