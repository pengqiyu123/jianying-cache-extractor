import os
from pathlib import Path

import pytest

from jianying_controller.models import CandidateStatus
from jianying_controller.media_validator import (
    validate_media_file,
    verify_copy,
    wait_until_stable,
)


def touch(path: Path, content: bytes = b"x", mtime: int = 1_700_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))


def test_validate_media_file_rejects_alpha_sidecar(tmp_path):
    path = tmp_path / "cache_video.alpha.mp4"
    touch(path, b"fake")

    result = validate_media_file(path)

    assert result.status == CandidateStatus.REJECTED
    assert result.reason == "alpha_sidecar"


def test_validate_media_file_returns_available_video(tmp_path, monkeypatch):
    path = tmp_path / "cache_video.mp4"
    touch(path, b"fake mp4")

    monkeypatch.setattr(
        "jianying_controller.media_validator.inspect_video",
        lambda media_path: (1920, 1080, 124000.0),
    )

    result = validate_media_file(path)

    assert result.status == CandidateStatus.AVAILABLE
    assert result.width == 1920
    assert result.height == 1080
    assert result.duration_ms == 124000.0
    assert result.reason is None


def test_wait_until_stable_detects_unchanged_file(tmp_path):
    path = tmp_path / "stable.mp4"
    touch(path, b"stable")

    assert wait_until_stable(path, samples=2, interval_seconds=0) is True


def test_verify_copy_checks_size(tmp_path):
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    touch(source, b"same")
    touch(target, b"same")

    assert verify_copy(source, target).size_verified is True

    target.write_bytes(b"different")
    assert verify_copy(source, target).size_verified is False
