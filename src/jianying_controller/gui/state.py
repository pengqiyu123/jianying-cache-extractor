"""Pure GUI state and presentation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..models import (
    CandidateStatus,
    CreateDraftRequest,
    MediaCandidate,
    ProcessStatus,
    SourceMode,
    WorkflowPhase,
)

APP_TITLE = "剪映缓存提取工具"
APP_VERSION = "v0.1"

BADGE_COLORS = {
    "ok": ("#0f7b33", "#d1fae5"),
    "busy": ("#a16207", "#fef3c7"),
    "muted": ("#6b7280", "#f3f4f6"),
    "error": ("#b91c1c", "#fee2e2"),
    "info": ("#1d4ed8", "#dbeafe"),
}

PROCESS_LABELS = {
    "not_installed": "未安装",
    "stopped": "未运行",
    "starting": "启动中",
    "running": "已打开",
    "background": "后台运行",
    "tray_only": "仅托盘",
}

REJECTION_LABELS = {
    "alpha_sidecar": "已跳过 alpha",
    "empty_file": "空文件",
    "invalid_dimensions": "尺寸无效",
    "invalid_duration": "时长无效",
    "media_not_found": "文件不存在",
    "missing_alpha_sidecar": "缺少 alpha 侧车文件",
    "alpha_unreadable": "alpha 文件不可读",
    "no_video_track": "无视频轨",
    "not_file": "不是文件",
    "not_mp4": "不是 MP4",
    "not_main_mp4": "非主 MP4",
    "read_failed": "读取失败",
    "still_writing": "正在生成",
}

PHASE_LABELS = {
    WorkflowPhase.IDLE: "准备中",
    WorkflowPhase.COMPOSITE_DONE: "复合片段已发送",
    WorkflowPhase.RESTARTED: "已重启",
    WorkflowPhase.IMPORTED: "导入已发送",
}

STATUS_MESSAGES = {
    "compound_sent": "已发送复合请求，等待缓存生成...",
    "restart_ready": "已重启，请打开目标项目",
    "import_sent": "已发送导入请求，请在剪映中确认",
    "draft_created": "草稿已创建，请回到剪映首页查看。",
}

USAGE_INSTRUCTIONS = """\
本工具通过剪映的复合片段预合成缓存定位可用视频。

使用流程：
① 选择近 30 分钟内修改的项目
② 确认剪映已打开该项目编辑界面
③ 发送复合片段快捷键并等待缓存生成
④ 只重启剪映主进程后重新打开目标项目
⑤ 使用剪映导入窗口导入缓存视频

注意：剪映没有默认的复合片段快捷键，需要手动设置。
本工具默认使用 Shift+G（推荐）。
设置方法：剪映菜单 → 设置 → 快捷键 → 搜索"复合片段"。
"""


@dataclass
class GuiState:
    selected_project_path: Path | None = None
    opened_project_confirmed: bool = False
    tracked_mp4_path: Path | None = None
    process_status: ProcessStatus = ProcessStatus.STOPPED
    workflow_phase: WorkflowPhase = WorkflowPhase.IDLE
    busy: bool = False


def human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def human_duration(duration_ms: float | None) -> str:
    if not duration_ms:
        return "-"
    return f"{duration_ms / 1000:.1f}s"


def resolution_label(w: int | None, h: int | None) -> str:
    if w and h:
        return f"{w}x{h}"
    return "-"


def _classification_display(status: str, reason: str | None, phase: WorkflowPhase = WorkflowPhase.IDLE) -> str:
    if status not in ("standard_importable", "private_importable"):
        if reason and reason in REJECTION_LABELS:
            return REJECTION_LABELS[reason]
        if reason:
            return reason
        return "不可导入"
    if phase in (WorkflowPhase.RESTARTED, WorkflowPhase.IMPORTED):
        return "可导入"
    if phase == WorkflowPhase.COMPOSITE_DONE:
        return "等待重启剪映"
    return "格式正确"


def _classification_tag(status: str, phase: WorkflowPhase = WorkflowPhase.IDLE) -> str:
    if status not in ("standard_importable", "private_importable"):
        return "rejected"
    if phase == WorkflowPhase.COMPOSITE_DONE:
        return "writing"
    return "available"


def _badge_style(tone: str) -> dict[str, str]:
    fg, bg = BADGE_COLORS.get(tone, BADGE_COLORS["muted"])
    return {"fg": fg, "bg": bg}


def _process_tone(status: ProcessStatus) -> str:
    if status == ProcessStatus.RUNNING:
        return "ok"
    if status in {ProcessStatus.STARTING, ProcessStatus.BACKGROUND, ProcessStatus.TRAY_ONLY}:
        return "busy"
    if status == ProcessStatus.NOT_INSTALLED:
        return "error"
    return "muted"


def _phase_tone(phase: WorkflowPhase) -> str:
    if phase == WorkflowPhase.IDLE:
        return "muted"
    return "info"


def button_states(
    *,
    process: ProcessStatus,
    phase: WorkflowPhase,
    selected_project: bool,
    confirmed_open: bool,
    tracked_mp4: bool,
    busy: bool,
) -> dict[str, bool]:
    if busy:
        return {key: False for key in ("scan", "create_draft", "compound", "restart", "auto_import", "uncompose")}
    return {
        "scan": selected_project,
        "create_draft": phase == WorkflowPhase.IDLE and tracked_mp4,
        "compound": process == ProcessStatus.RUNNING and selected_project and confirmed_open,
        "restart": phase == WorkflowPhase.COMPOSITE_DONE,
        "auto_import": process == ProcessStatus.RUNNING
        and phase == WorkflowPhase.RESTARTED
        and tracked_mp4
        and confirmed_open,
        "uncompose": process == ProcessStatus.RUNNING,
    }


def format_status_message(event: str, detail: str | None) -> str:
    if event == "cache_found" and detail:
        return f"已找到缓存视频: {detail}"
    return STATUS_MESSAGES.get(event, detail or "")


def candidate_row(candidate: MediaCandidate) -> tuple[str, str, str, str, str, str, str, str]:
    modified = candidate.modified_at.strftime("%Y-%m-%d %H:%M:%S") if candidate.modified_at else "-"
    return (
        candidate.path.name,
        _origin_label(candidate),
        human_size(candidate.size_bytes),
        human_duration(candidate.duration_ms),
        resolution_label(candidate.width, candidate.height),
        modified,
        _candidate_status_label(candidate),
        str(candidate.path),
    )


def build_request(
    mode: SourceMode,
    *,
    project_path: Path | None = None,
    mp4_path: Path | None = None,
    source_name: str | None = None,
    selected_media_path: Path | None = None,
    draft_name: str | None = None,
) -> CreateDraftRequest:
    return CreateDraftRequest(
        mode=mode,
        project_path=project_path,
        mp4_path=mp4_path,
        source_name=source_name,
        selected_media_path=selected_media_path,
        draft_name=draft_name,
    )


def status_label(status: str) -> str:
    labels = {
        "detected": "已找到候选视频。",
        "validated": "视频可用于创建草稿。",
        "copying": "正在复制视频。",
        "copied": "视频已复制到新草稿目录。",
        "draft_created": "草稿已创建，请回到剪映首页查看。",
        "user_verified_openable": "用户已确认剪映可见/可打开。",
        "failed": "操作失败。",
    }
    return labels.get(status, status)


def empty_state_message(
    mode: SourceMode,
    candidates: list[MediaCandidate] | None = None,
    *,
    error_code: str | None = None,
    process_status: str | None = None,
) -> str:
    candidates = candidates or []
    reason = _first_rejection_reason(candidates)
    reason_text = f" {reason}" if reason else ""
    if mode == SourceMode.AUTO and (error_code == "no_active_project" or process_status in {"background", "stopped"}):
        return "未检测到剪映运行。仍可手动选择项目或 MP4。"
    if mode == SourceMode.MP4:
        return f"这个 MP4 暂不可用。{reason_text}".strip()
    if mode == SourceMode.PROJECT:
        return f"最近半小时没有找到可用的复合片段缓存。{reason_text}".strip()
    return "没有找到可用候选，请手动选择项目或 MP4。"


def _origin_label(candidate: MediaCandidate) -> str:
    labels = {
        "project": "项目缓存",
        "cloud_cache": "cloud_cache 镜像",
        "manual_file": "手动 MP4",
    }
    return labels.get(candidate.origin.value, candidate.origin.value)


def _candidate_status_label(candidate: MediaCandidate) -> str:
    if candidate.status == CandidateStatus.AVAILABLE:
        return "可用"
    if candidate.status == CandidateStatus.WRITING:
        return "正在生成"
    if candidate.rejection_reason:
        return REJECTION_LABELS.get(candidate.rejection_reason, candidate.rejection_reason)
    return "不可用"


def _first_rejection_reason(candidates: list[MediaCandidate]) -> str | None:
    for candidate in candidates:
        if candidate.rejection_reason:
            return REJECTION_LABELS.get(candidate.rejection_reason, candidate.rejection_reason)
    return None
