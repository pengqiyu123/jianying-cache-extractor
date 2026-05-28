import json
import os
from pathlib import Path

import pytest

from jianying_controller import draft_creator
from jianying_controller.draft_creator import create_extracted_draft


def touch(path: Path, content: bytes = b"x", mtime: int = 1_700_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))


class FakeVideoMaterial:
    def __init__(self, path):
        self.path = str(path)
        self.width = 1280
        self.height = 720
        self.duration = 1234567


class FakeVideoSegment:
    def __init__(self, material, timerange):
        self.material = material
        self.timerange = timerange


class FakeScript:
    def __init__(self, draft_path, *, fail_save=False):
        self.draft_path = draft_path
        self.fail_save = fail_save
        self.segments = []

    def add_track(self, track_type):
        self.track_type = track_type
        return self

    def add_segment(self, segment):
        self.segments.append(segment)
        return self

    def save(self):
        if self.fail_save:
            raise RuntimeError("save failed")
        (self.draft_path / "draft_content.json").write_text(
            json.dumps({"segments": len(self.segments)}),
            encoding="utf-8",
        )


class FakeDraftFolder:
    fail_save = False

    def __init__(self, draft_dir):
        self.draft_dir = Path(draft_dir)

    def create_draft(self, name, width, height, fps=30, allow_replace=False):
        draft_path = self.draft_dir / name
        draft_path.mkdir(parents=True, exist_ok=allow_replace)
        (draft_path / "draft_meta_info.json").write_text("{}", encoding="utf-8")
        return FakeScript(draft_path, fail_save=self.fail_save)


class FakeDraftModule:
    DraftFolder = FakeDraftFolder
    VideoMaterial = FakeVideoMaterial
    VideoSegment = FakeVideoSegment

    class TrackType:
        video = "video"

    @staticmethod
    def trange(start, duration):
        return (start, duration)


def install_fake_draft(monkeypatch, *, fail_save=False):
    FakeDraftFolder.fail_save = fail_save
    monkeypatch.setattr(draft_creator, "draft", FakeDraftModule)
    monkeypatch.setattr(draft_creator, "inspect_video", lambda path: (1280, 720, 1234))


def test_create_extracted_draft_rolls_back_partial_draft_on_save_failure(tmp_path, monkeypatch):
    install_fake_draft(monkeypatch, fail_save=True)
    source = tmp_path / "source.mp4"
    touch(source, b"mp4 bytes")
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()

    with pytest.raises(RuntimeError, match="save failed"):
        create_extracted_draft(draft_root, source, "Rollback Project")

    assert list(draft_root.iterdir()) == []


def test_create_extracted_draft_generates_unique_names_in_same_second(tmp_path, monkeypatch):
    install_fake_draft(monkeypatch)
    source = tmp_path / "source.mp4"
    touch(source, b"mp4 bytes")
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()

    class FixedDateTime:
        @staticmethod
        def now():
            return FixedDateTime()

        def strftime(self, pattern):
            return "20260528_210210"

    monkeypatch.setattr(draft_creator, "datetime", FixedDateTime)

    first = create_extracted_draft(draft_root, source, "Same Second")
    second = create_extracted_draft(draft_root, source, "Same Second")

    assert first.name == "提取_Same Second_20260528_210210"
    assert second.name == "提取_Same Second_20260528_210210_2"
    assert first.draft_path.exists()
    assert second.draft_path.exists()
