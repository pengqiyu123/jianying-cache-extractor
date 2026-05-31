from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from jianying_controller.cache_extractor import find_combination_mp4s, scan_latest_cache
from jianying_controller.draft_detector import detect_recent_drafts
from jianying_controller.media_validator import is_file_stable, validate_video


def test_detect_recent_drafts_returns_all_recent_projects_sorted(tmp_path, monkeypatch) -> None:
    import jianying_controller.draft_detector as detector

    old_project = tmp_path / "old"
    recent_a = tmp_path / "recent-a"
    recent_b = tmp_path / "recent-b"
    for project in (old_project, recent_a, recent_b):
        project.mkdir()
    (recent_b / "Resources" / "combination").mkdir(parents=True)

    now = datetime.now()
    times = {
        old_project: now - timedelta(hours=1),
        recent_a: now - timedelta(minutes=10),
        recent_b: now - timedelta(minutes=2),
    }
    monkeypatch.setattr(detector, "_project_modified_at", lambda path: times[path])

    drafts = detect_recent_drafts(tmp_path, recent_minutes=30)

    assert [draft.name for draft in drafts] == ["recent-b", "recent-a"]
    assert drafts[0].has_combination_cache is True
    assert drafts[1].has_combination_cache is False


def test_find_combination_mp4s_skips_alpha_empty_and_old_files(tmp_path) -> None:
    combination = tmp_path / "Project" / "Resources" / "combination"
    combination.mkdir(parents=True)
    main = combination / "A_video.mp4"
    alpha = combination / "A_video.mp4.alpha.mp4"
    empty = combination / "empty_video.mp4"
    old = combination / "old_video.mp4"
    main.write_bytes(b"main")
    alpha.write_bytes(b"alpha")
    empty.write_bytes(b"")
    old.write_bytes(b"old")
    old_time = datetime.now() - timedelta(hours=2)
    os.utime(old, (old_time.timestamp(), old_time.timestamp()))

    files = find_combination_mp4s(tmp_path / "Project", require_video=False, recent_seconds=1800)

    assert [file.path.name for file in files] == ["A_video.mp4"]
    assert scan_latest_cache(tmp_path / "Project", require_video=False) == main


def test_is_file_stable_uses_two_size_samples(tmp_path) -> None:
    path = tmp_path / "stable.mp4"
    path.write_bytes(b"stable")

    assert is_file_stable(path, interval=0)


def test_validate_video_returns_none_for_unparseable_file(tmp_path) -> None:
    path = tmp_path / "not-real.mp4"
    path.write_bytes(b"not a real mp4")

    assert validate_video(path) is None
