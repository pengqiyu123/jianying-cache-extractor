import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "src")

from jianying_controller.cache_extractor import find_combination_mp4s
from jianying_controller.draft_creator import create_extracted_draft
from jianying_controller.process import ProcessStatus
from jianying_controller.project_detector import detect_active_project


class StubProcess:
    def __init__(self, status):
        self._status = status

    def status(self):
        return self._status


def touch(path: Path, content: bytes = b"x", mtime: int = 1_700_000_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))


def test_find_combination_mp4s_filters_and_sorts(tmp_path):
    project = tmp_path / "draft"
    combo = project / "Resources" / "combination"
    touch(combo / "old_video.mp4", b"old", 100)
    touch(combo / "new_video.mp4", b"new", 200)
    touch(combo / "new_video.alpha.mp4", b"alpha", 300)
    touch(combo / "empty_video.mp4", b"", 400)
    touch(combo / "note.txt", b"text", 500)

    files = find_combination_mp4s(project, require_video=False)

    assert [f.path.name for f in files] == ["new_video.mp4", "old_video.mp4"]
    assert files[0].size_bytes == 3


def test_find_combination_mp4s_requires_video_by_default(tmp_path):
    project = tmp_path / "draft"
    combo = project / "Resources" / "combination"
    touch(combo / "cache_video.mp4", b"not a real mp4", 100)

    assert find_combination_mp4s(project) == []


def test_detect_active_project_requires_running_and_combination(tmp_path, monkeypatch):
    active = tmp_path / "Active"
    inactive = tmp_path / "Inactive"
    touch(active / "draft_content.json", b"encrypted", 500)
    touch(active / "Resources" / "combination" / "cache_video.mp4", b"cache", 400)
    touch(inactive / "draft_content.json", b"encrypted", 600)

    import jianying_controller.cache_extractor as cache_extractor

    monkeypatch.setattr(cache_extractor, "inspect_video", lambda path: (1920, 1080, 1000))
    result = detect_active_project(tmp_path, process=StubProcess(ProcessStatus.RUNNING))

    assert result is not None
    assert result.name == "Active"
    assert result.latest_mp4 is not None
    assert result.latest_mp4.name == "cache_video.mp4"

    stopped = detect_active_project(tmp_path, process=StubProcess(ProcessStatus.STOPPED))
    assert stopped is None


def test_detect_active_project_uses_cloud_cache_mirror(tmp_path, monkeypatch):
    active = tmp_path / "5月28日 (1)-副本"
    touch(active / "draft_content.json", b"encrypted", 900)
    touch(active / "Resources" / "combination" / "broken_video.mp4", b"not mp4", 800)
    mirror_cache = (
        tmp_path
        / ".cloud_cache_1544148301652168"
        / active.name
        / "Resources"
        / "combination"
        / "valid_video.mp4"
    )
    touch(mirror_cache, b"valid", 700)

    import jianying_controller.cache_extractor as cache_extractor

    def fake_inspect(path):
        return (1920, 1080, 1000) if Path(path).name == "valid_video.mp4" else None

    monkeypatch.setattr(cache_extractor, "inspect_video", fake_inspect)

    result = detect_active_project(tmp_path, process=StubProcess(ProcessStatus.RUNNING))

    assert result is not None
    assert result.name == active.name
    assert result.path == active
    assert result.latest_mp4 == mirror_cache


def test_create_extracted_draft_copies_mp4_and_writes_draft(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    touch(source, b"fake mp4 bytes", 100)

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
        def __init__(self, draft_path):
            self.draft_path = draft_path
            self.segments = []

        def add_track(self, track_type):
            self.track_type = track_type
            return self

        def add_segment(self, segment):
            self.segments.append(segment)
            return self

        def save(self):
            (self.draft_path / "draft_content.json").write_text(
                json.dumps({"segments": len(self.segments)}),
                encoding="utf-8",
            )

    class FakeDraftFolder:
        def __init__(self, draft_dir):
            self.draft_dir = Path(draft_dir)

        def create_draft(self, name, width, height, fps=30, allow_replace=False):
            draft_path = self.draft_dir / name
            draft_path.mkdir(parents=True, exist_ok=allow_replace)
            (draft_path / "draft_meta_info.json").write_text("{}", encoding="utf-8")
            return FakeScript(draft_path)

    class FakeDraftModule:
        DraftFolder = FakeDraftFolder
        VideoMaterial = FakeVideoMaterial
        VideoSegment = FakeVideoSegment

        class TrackType:
            video = "video"

        @staticmethod
        def trange(start, duration):
            return (start, duration)

    from jianying_controller import draft_creator

    monkeypatch.setattr(draft_creator, "draft", FakeDraftModule)
    monkeypatch.setattr(draft_creator, "inspect_video", lambda path: (1280, 720, 1234))

    draft_root = tmp_path / "drafts"
    draft_root.mkdir()

    result = create_extracted_draft(draft_root, source, "Source Project")

    assert result.draft_path.name.startswith("提取_Source Project_")
    copied = result.media_path
    assert copied.exists()
    assert copied.read_bytes() == b"fake mp4 bytes"
    assert (result.draft_path / "draft_content.json").exists()
