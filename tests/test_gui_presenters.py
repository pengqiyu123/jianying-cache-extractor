from datetime import datetime
from pathlib import Path

from jianying_controller.gui import PROCESS_LABELS, build_request, candidate_row, empty_state_message, status_label
from jianying_controller.models import CacheOrigin, CandidateStatus, MediaCandidate, SourceMode


def make_candidate(**overrides):
    values = {
        "path": Path(r"D:\cache\video.mp4"),
        "origin": CacheOrigin.CLOUD_CACHE,
        "source_project_name": "项目A",
        "size_bytes": 122259945,
        "modified_at": datetime(2026, 5, 28, 21, 1, 46),
        "width": 1920,
        "height": 1080,
        "duration_ms": 124367.0,
        "status": CandidateStatus.AVAILABLE,
        "score": 130,
        "rejection_reason": None,
    }
    values.update(overrides)
    return MediaCandidate(**values)


def test_candidate_row_formats_available_cloud_cache_candidate():
    row = candidate_row(make_candidate())

    assert row == (
        "video.mp4",
        "cloud_cache 镜像",
        "116.6 MB",
        "124.4s",
        "1920x1080",
        "2026-05-28 21:01:46",
        "可用",
        r"D:\cache\video.mp4",
    )


def test_candidate_row_formats_rejected_reason():
    row = candidate_row(
        make_candidate(
            status=CandidateStatus.REJECTED,
            width=None,
            height=None,
            duration_ms=None,
            rejection_reason="no_video_track",
        )
    )

    assert row[3] == "-"
    assert row[4] == "-"
    assert row[6] == "无视频轨"


def test_build_request_supports_three_modes():
    assert build_request(SourceMode.AUTO).mode == SourceMode.AUTO
    assert build_request(SourceMode.PROJECT, project_path=Path(r"D:\drafts\项目A")).project_path == Path(
        r"D:\drafts\项目A"
    )
    assert build_request(SourceMode.MP4, mp4_path=Path(r"D:\video.mp4"), source_name="手动").source_name == "手动"


def test_status_label_is_truthful():
    assert status_label("draft_created") == "草稿已创建，请回到剪映首页查看。"
    assert "导出" not in status_label("draft_created")


def test_empty_state_mentions_recent_window_for_project_cache():
    assert "最近半小时" in empty_state_message(SourceMode.PROJECT, [])


def test_empty_state_auto_after_exit_prefers_manual_guidance():
    message = empty_state_message(SourceMode.AUTO, error_code="no_active_project", process_status="background")

    assert "未检测到剪映运行" in message
    assert "手动选择项目或 MP4" in message
    assert "最近活跃" not in message


def test_empty_state_mp4_rejected_shows_specific_reason():
    message = empty_state_message(
        SourceMode.MP4,
        [make_candidate(status=CandidateStatus.REJECTED, rejection_reason="no_video_track")],
    )

    assert "无视频轨" in message
    assert "最近半小时" not in message


def test_process_labels_distinguish_visible_window_from_background_process():
    assert PROCESS_LABELS["running"] == "已打开"
    assert PROCESS_LABELS["background"] == "后台运行"
