from __future__ import annotations

import json
from pathlib import Path

from jianying_controller.draft_creator import safe_draft_name
from jianying_controller.private_cache_draft import create_private_cache_draft
from jianying_controller.private_cache_scan import inspect_private_cache


def test_safe_draft_name_removes_windows_invalid_chars() -> None:
    cleaned = safe_draft_name('a<b>:"/\\|?*\x00 c')

    assert cleaned.startswith("a_b")
    assert not any(char in cleaned for char in '<>:"/\\|?*\x00')


def test_private_cache_uses_alpha_sidecar_shape_without_parsing_main(monkeypatch, tmp_path) -> None:
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    main = tmp_path / "ABC_video.mp4"
    alpha = tmp_path / "ABC_video.mp4.alpha.mp4"
    main.write_bytes(b"private bdve crpt")
    alpha.write_bytes(b"alpha")

    monkeypatch.setattr("jianying_controller.private_cache_draft.validate_video", lambda path: (1920, 1080, 1234.0))

    created = create_private_cache_draft(draft_root, main, "source")
    content = json.loads((created.draft_path / "draft_content.json").read_text(encoding="utf-8"))

    assert created.draft_path.exists()
    assert content["canvas_config"]["width"] == 1920
    assert content["canvas_config"]["height"] == 1080
    assert content["duration"] == 1_234_000
    assert (created.draft_path / "Resources" / "combination" / main.name).exists()
    assert (created.draft_path / "Resources" / "combination" / alpha.name).exists()


def test_private_cache_scan_classifies_private_with_alpha(monkeypatch, tmp_path) -> None:
    main = tmp_path / "ABC_video.mp4"
    alpha = tmp_path / "ABC_video.mp4.alpha.mp4"
    main.write_bytes(b"private bdve crpt")
    alpha.write_bytes(b"alpha")
    monkeypatch.setattr("jianying_controller.private_cache_scan.validate_video", lambda path: None if path == main else (1280, 720, 2000.0))

    result = inspect_private_cache(main)

    assert result.status == "private_importable"
    assert result.width == 1280
    assert result.height == 720
    assert result.duration_ms == 2000.0
