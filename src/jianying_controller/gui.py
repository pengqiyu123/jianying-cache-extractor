"""Tkinter GUI for extracting JianYing combination caches."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Iterable

from .env import JianYingEnv
from .models import (
    CacheOrigin,
    CandidateStatus,
    CreateDraftRequest,
    CreatedDraft,
    MediaCandidate,
    ResolvedSource,
    SourceMode,
    WorkflowError,
)
from .process import JianYingProcess
from .workflow import create_draft_from_source, scan_source


APP_TITLE = "剪映缓存提取 v0.1"

STATUS_COLORS = {
    "ok": ("#0f7b33", "#e8f5ec"),
    "busy": ("#a16207", "#fff7db"),
    "muted": ("#6b7280", "#f3f4f6"),
    "error": ("#b91c1c", "#fee2e2"),
    "info": ("#1d4ed8", "#dbeafe"),
}

ORIGIN_LABELS = {
    CacheOrigin.PROJECT: "项目目录",
    CacheOrigin.CLOUD_CACHE: "cloud_cache 镜像",
    CacheOrigin.MANUAL_FILE: "手动文件",
}

REJECTION_LABELS = {
    "alpha_sidecar": "已跳过 alpha",
    "empty_file": "空文件",
    "invalid_dimensions": "尺寸无效",
    "invalid_duration": "时长无效",
    "media_not_found": "文件不存在",
    "no_video_track": "无视频轨",
    "not_file": "不是文件",
    "not_mp4": "不是 MP4",
    "read_failed": "读取失败",
    "still_writing": "正在生成",
}

PROCESS_LABELS = {
    "not_installed": "未安装",
    "stopped": "未运行",
    "starting": "启动中",
    "running": "已打开",
    "background": "后台运行",
    "tray_only": "仅托盘",
}

EMPTY_STATE_BY_MODE = {
    SourceMode.AUTO: "没有找到最近活跃的剪映项目，请手动选择项目。",
    SourceMode.PROJECT: "最近半小时内没有可用的复合片段缓存。请在剪映中完成预合成后重试。",
    SourceMode.MP4: "请选择一个可导入的 MP4 文件。",
}

EMPTY_STATE_BY_ERROR = {
    "no_active_project": EMPTY_STATE_BY_MODE[SourceMode.AUTO],
    "project_required": "请选择剪映项目目录。",
    "project_not_found": "项目目录不存在，请重新选择。",
    "mp4_required": EMPTY_STATE_BY_MODE[SourceMode.MP4],
    "media_not_found": "媒体文件不存在，请重新选择。",
    "no_valid_media": "未找到可导入的视频缓存。",
}

MODE_HELP_TEXT = {
    SourceMode.AUTO: "请先在剪映中完成复合片段预合成。工具会查找最近活跃项目和 cloud_cache 缓存。",
    SourceMode.PROJECT: "选择一个剪映项目目录，工具会同时扫描同名 cloud_cache 镜像。",
    SourceMode.MP4: "选择一个本地 MP4，工具会把它创建为新的剪映草稿。",
}


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


def resolution_label(candidate: MediaCandidate) -> str:
    if candidate.width and candidate.height:
        return f"{candidate.width}x{candidate.height}"
    return "-"


def candidate_status_label(candidate: MediaCandidate) -> str:
    if candidate.status == CandidateStatus.AVAILABLE:
        return "可用"
    if candidate.status == CandidateStatus.WRITING:
        return "正在生成"
    if candidate.rejection_reason:
        return REJECTION_LABELS.get(candidate.rejection_reason, candidate.rejection_reason)
    return "不可用"


def candidate_tag(candidate: MediaCandidate) -> str:
    if candidate.status == CandidateStatus.AVAILABLE:
        return "available"
    if candidate.status == CandidateStatus.WRITING:
        return "writing"
    return "rejected"


def sort_candidates_for_display(candidates: Iterable[MediaCandidate]) -> list[MediaCandidate]:
    """Return candidates in the order a user should review them."""
    status_rank = {
        CandidateStatus.AVAILABLE: 0,
        CandidateStatus.WRITING: 1,
        CandidateStatus.REJECTED: 2,
    }
    return sorted(
        candidates,
        key=lambda candidate: (
            status_rank.get(candidate.status, 99),
            -candidate.score,
            -candidate.size_bytes,
            -candidate.modified_at.timestamp(),
            str(candidate.path).lower(),
        ),
    )


def candidate_row(candidate: MediaCandidate) -> tuple[str, str, str, str, str, str, str, str]:
    """Return Treeview-ready values for a media candidate."""
    return (
        candidate.path.name,
        ORIGIN_LABELS.get(candidate.origin, candidate.origin.value),
        human_size(candidate.size_bytes),
        human_duration(candidate.duration_ms),
        resolution_label(candidate),
        candidate.modified_at.strftime("%Y-%m-%d %H:%M:%S"),
        candidate_status_label(candidate),
        str(candidate.path),
    )


def candidate_summary(candidate: MediaCandidate | None) -> str:
    if candidate is None:
        return "未选择缓存视频。"
    return (
        f"已选择：{candidate.path.name} · {ORIGIN_LABELS.get(candidate.origin, candidate.origin.value)} · "
        f"{human_size(candidate.size_bytes)} · {human_duration(candidate.duration_ms)} · "
        f"{resolution_label(candidate)} · {candidate_status_label(candidate)}"
    )


def status_label(status: str) -> str:
    labels = {
        "detected": "已找到候选视频，请确认后创建剪映草稿。",
        "validated": "视频可用。",
        "copying": "正在复制视频。",
        "creating": "正在创建草稿...",
        "copied": "视频已复制到新草稿目录。",
        "draft_created": "草稿已创建，请回到剪映首页查看。",
        "user_verified_openable": "用户已确认剪映可见/可打开。",
        "failed": "操作失败。",
    }
    return labels.get(status, status)


def empty_state_message(
    mode: SourceMode | str,
    candidates: Iterable[MediaCandidate] | None = None,
    *,
    error_code: str | None = None,
    process_status: str | None = None,
) -> str:
    """Return product-facing guidance for empty or unavailable scan results."""
    try:
        source_mode = SourceMode(mode)
    except ValueError:
        source_mode = SourceMode.AUTO

    if source_mode == SourceMode.AUTO and process_status in {"not_installed", "stopped", "tray_only", "background"}:
        return "未检测到剪映运行主窗口。仍可手动选择项目或 MP4。"
    if error_code in EMPTY_STATE_BY_ERROR:
        return EMPTY_STATE_BY_ERROR[error_code]

    candidate_list = list(candidates or [])
    if any(candidate.status == CandidateStatus.WRITING for candidate in candidate_list):
        if source_mode == SourceMode.MP4:
            return "此 MP4 仍在写入，请稍后重试。"
        return "缓存文件仍在生成，请稍后重新检测。"
    if any(candidate.status == CandidateStatus.REJECTED for candidate in candidate_list):
        if source_mode == SourceMode.MP4:
            rejected = next(candidate for candidate in candidate_list if candidate.status == CandidateStatus.REJECTED)
            reason = REJECTION_LABELS.get(rejected.rejection_reason or "", rejected.rejection_reason or "不可导入")
            return f"此 MP4 不可导入：{reason}。请重新选择一个标准 MP4 文件。"
        reasons = _rejection_summary(candidate_list)
        if reasons:
            return f"最近半小时内找到缓存文件，但都不是可导入视频：{reasons}。请完成预合成后重新检测。"
        return "最近半小时内找到缓存文件，但都不是可导入视频。请完成预合成后重新检测。"
    return EMPTY_STATE_BY_MODE[source_mode]


def _rejection_summary(candidates: Iterable[MediaCandidate]) -> str:
    labels: list[str] = []
    for candidate in candidates:
        if candidate.status != CandidateStatus.REJECTED or not candidate.rejection_reason:
            continue
        label = REJECTION_LABELS.get(candidate.rejection_reason, candidate.rejection_reason)
        if label not in labels:
            labels.append(label)
        if len(labels) >= 3:
            break
    return "、".join(labels)


def safe_error_message(exc: Exception) -> str:
    """Keep GUI errors useful without leaking Python tracebacks."""
    if isinstance(exc, WorkflowError):
        message = exc.message
    else:
        message = str(exc) or "操作失败，请稍后重试。"
    if "Traceback" in message or "\n" in message:
        return "操作失败，请查看日志后重试。"
    return message


def build_request(
    mode: SourceMode,
    *,
    project_path: Path | None = None,
    mp4_path: Path | None = None,
    source_name: str | None = None,
    selected_media_path: Path | None = None,
) -> CreateDraftRequest:
    return CreateDraftRequest(
        mode=mode,
        project_path=project_path,
        mp4_path=mp4_path,
        source_name=source_name or None,
        selected_media_path=selected_media_path,
    )


class CacheExtractorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(900, 580)

        self.env = JianYingEnv()
        self.process = JianYingProcess(self.env)
        self.source: ResolvedSource | None = None
        self.created: CreatedDraft | None = None
        self.candidates: list[MediaCandidate] = []
        self._candidate_by_iid: dict[str, MediaCandidate] = {}

        self.mode_var = tk.StringVar(value=SourceMode.AUTO.value)
        self.status_var = tk.StringVar(value="正在检测环境...")
        self.process_var = tk.StringVar(value="-")
        self.draft_dir_var = tk.StringVar(value="-")
        self.source_var = tk.StringVar(value="-")
        self.project_path_var = tk.StringVar(value="")
        self.mp4_path_var = tk.StringVar(value="")
        self.source_name_var = tk.StringVar(value="")
        self.created_var = tk.StringVar(value="")
        self.empty_var = tk.StringVar(value="")
        self.last_scan_var = tk.StringVar(value="-")
        self.phase_var = tk.StringVar(value="准备中")
        self.mode_help_var = tk.StringVar(value=MODE_HELP_TEXT[SourceMode.AUTO])
        self.selected_var = tk.StringVar(value=candidate_summary(None))
        self.selected_path_var = tk.StringVar(value="-")
        self.result_name_var = tk.StringVar(value="-")
        self.result_path_var = tk.StringVar(value="-")
        self.result_verify_var = tk.StringVar(value="-")
        self.log_visible_var = tk.BooleanVar(value=False)
        self._is_scanning = False
        self._is_creating = False
        self._ui_events: queue.Queue = queue.Queue()

        self._build_ui()
        self.after(50, self._drain_ui_events)
        self.after(100, self.refresh_environment)
        self.after(300, self.scan_current_source)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            root,
            text="把剪映复合片段预合成缓存，创建成一个新的剪映草稿。",
            font=("", 11, "bold"),
        ).pack(fill=tk.X, pady=(0, 10))

        environment = ttk.LabelFrame(root, text="环境")
        environment.pack(fill=tk.X)
        environment.columnconfigure(1, weight=1)
        environment.columnconfigure(3, weight=1)
        ttk.Label(environment, text="剪映状态").grid(row=0, column=0, sticky=tk.W, padx=(10, 8), pady=(8, 2))
        self.process_badge = tk.Label(environment, textvariable=self.process_var, padx=8, pady=2)
        self.process_badge.grid(row=0, column=1, sticky=tk.W, pady=(8, 2))
        ttk.Label(environment, text="最近检测").grid(row=0, column=2, sticky=tk.W, padx=(18, 8), pady=(8, 2))
        ttk.Label(environment, textvariable=self.last_scan_var).grid(row=0, column=3, sticky=tk.W, pady=(8, 2))
        ttk.Label(environment, text="草稿目录").grid(row=1, column=0, sticky=tk.W, padx=(10, 8), pady=(2, 8))
        ttk.Label(environment, textvariable=self.draft_dir_var).grid(
            row=1,
            column=1,
            columnspan=3,
            sticky=tk.EW,
            pady=(2, 8),
        )

        source_group = ttk.LabelFrame(root, text="1. 选择来源")
        source_group.pack(fill=tk.X, pady=(10, 8))
        mode_bar = ttk.Frame(source_group)
        mode_bar.pack(fill=tk.X, padx=10, pady=(8, 4))
        self.mode_buttons: list[ttk.Radiobutton] = []
        for mode, label in (
            (SourceMode.AUTO, "自动识别"),
            (SourceMode.PROJECT, "选择项目"),
            (SourceMode.MP4, "选择 MP4"),
        ):
            button = ttk.Radiobutton(
                mode_bar,
                text=label,
                value=mode.value,
                variable=self.mode_var,
                command=self.on_mode_changed,
            )
            button.pack(side=tk.LEFT, padx=(0, 12))
            self.mode_buttons.append(button)
        ttk.Label(source_group, textvariable=self.mode_help_var, foreground="#4b5563").pack(
            fill=tk.X,
            padx=10,
            pady=(0, 8),
        )

        self.source_frame = ttk.Frame(source_group)
        self.source_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.auto_frame = ttk.Frame(self.source_frame)
        ttk.Label(self.auto_frame, text="来源").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self.auto_frame, textvariable=self.source_var).pack(side=tk.LEFT)

        self.project_frame = ttk.Frame(self.source_frame)
        self.project_entry = ttk.Entry(self.project_frame, textvariable=self.project_path_var)
        self.project_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.project_button = ttk.Button(self.project_frame, text="选择项目", command=self.choose_project)
        self.project_button.pack(side=tk.LEFT, padx=(8, 0))

        self.mp4_frame = ttk.Frame(self.source_frame)
        self.mp4_entry = ttk.Entry(self.mp4_frame, textvariable=self.mp4_path_var)
        self.mp4_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.mp4_button = ttk.Button(self.mp4_frame, text="选择 MP4", command=self.choose_mp4)
        self.mp4_button.pack(side=tk.LEFT, padx=(8, 0))

        status_bar = ttk.Frame(source_group)
        status_bar.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Label(status_bar, text="阶段").pack(side=tk.LEFT)
        self.phase_badge = tk.Label(status_bar, textvariable=self.phase_var, padx=8, pady=2)
        self.phase_badge.pack(side=tk.LEFT, padx=(8, 12))
        ttk.Label(status_bar, textvariable=self.status_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=120)
        self.progress.pack(side=tk.RIGHT)

        candidates_group = ttk.LabelFrame(root, text="2. 选择缓存视频")
        candidates_group.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(candidates_group, textvariable=self.empty_var, foreground="#6b7280").pack(
            fill=tk.X,
            padx=10,
            pady=(8, 4),
        )
        columns = ("name", "origin", "size", "duration", "resolution", "modified", "status", "path")
        tree_area = ttk.Frame(candidates_group)
        tree_area.pack(fill=tk.BOTH, expand=True, padx=10)
        self.tree = ttk.Treeview(tree_area, columns=columns, show="headings", height=8)
        self.tree.tag_configure("available", foreground="#0f7b33")
        self.tree.tag_configure("writing", foreground="#a16207")
        self.tree.tag_configure("rejected", foreground="#6b7280")
        headings = {
            "name": "缓存文件",
            "origin": "来源",
            "size": "大小",
            "duration": "时长",
            "resolution": "分辨率",
            "modified": "修改时间",
            "status": "状态",
            "path": "路径",
        }
        widths = {
            "name": 230,
            "origin": 110,
            "size": 90,
            "duration": 80,
            "resolution": 90,
            "modified": 150,
            "status": 110,
            "path": 0,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=0 if column == "path" else 20,
                stretch=column != "path",
                anchor=tk.W,
            )
        scrollbar = ttk.Scrollbar(tree_area, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.on_candidate_selected)

        ttk.Label(candidates_group, textvariable=self.selected_var).pack(fill=tk.X, padx=10, pady=(8, 2))
        ttk.Label(candidates_group, textvariable=self.selected_path_var, foreground="#6b7280").pack(
            fill=tk.X,
            padx=10,
            pady=(0, 8),
        )

        create_group = ttk.LabelFrame(root, text="3. 创建剪映草稿")
        create_group.pack(fill=tk.X, pady=(0, 8))
        create_group.columnconfigure(1, weight=1)
        ttk.Label(create_group, text="草稿名前缀").grid(row=0, column=0, sticky=tk.W, padx=(10, 8), pady=10)
        self.output_name_entry = ttk.Entry(create_group, textvariable=self.source_name_var)
        self.output_name_entry.grid(row=0, column=1, sticky=tk.EW, pady=10)
        self.scan_button = ttk.Button(create_group, text="重新检测", command=self.scan_current_source)
        self.scan_button.grid(row=0, column=2, padx=(10, 0), pady=10)
        self.create_button = ttk.Button(
            create_group,
            text="创建剪映草稿",
            command=self.create_selected,
            state=tk.DISABLED,
        )
        self.create_button.grid(row=0, column=3, padx=10, pady=10)

        result_group = ttk.LabelFrame(root, text="创建结果")
        result_group.pack(fill=tk.X, pady=(0, 8))
        result_group.columnconfigure(1, weight=1)
        ttk.Label(result_group, textvariable=self.created_var, font=("", 10, "bold")).grid(
            row=0,
            column=0,
            columnspan=4,
            sticky=tk.W,
            padx=10,
            pady=(8, 4),
        )
        ttk.Label(result_group, text="草稿名").grid(row=1, column=0, sticky=tk.W, padx=(10, 8), pady=2)
        ttk.Label(result_group, textvariable=self.result_name_var).grid(row=1, column=1, sticky=tk.W, pady=2)
        ttk.Label(result_group, text="复制校验").grid(row=1, column=2, sticky=tk.W, padx=(18, 8), pady=2)
        ttk.Label(result_group, textvariable=self.result_verify_var).grid(row=1, column=3, sticky=tk.W, pady=2)
        ttk.Label(result_group, text="草稿路径").grid(row=2, column=0, sticky=tk.W, padx=(10, 8), pady=(2, 8))
        ttk.Label(result_group, textvariable=self.result_path_var).grid(
            row=2,
            column=1,
            columnspan=3,
            sticky=tk.EW,
            pady=(2, 8),
        )
        self.open_button = ttk.Button(result_group, text="打开草稿目录", command=self.open_created_dir, state=tk.DISABLED)
        self.open_button.grid(row=3, column=0, padx=(10, 8), pady=(0, 10), sticky=tk.W)
        self.confirm_button = ttk.Button(
            result_group,
            text="我已在剪映确认可打开",
            command=self.confirm_user_verified,
            state=tk.DISABLED,
        )
        self.confirm_button.grid(row=3, column=1, pady=(0, 10), sticky=tk.W)

        diagnostics_header = ttk.Frame(root)
        diagnostics_header.pack(fill=tk.X)
        self.log_toggle_button = ttk.Button(diagnostics_header, text="显示诊断日志", command=self.toggle_log)
        self.log_toggle_button.pack(side=tk.LEFT)
        self.log_frame = ttk.LabelFrame(root, text="诊断日志")
        self.log = tk.Text(self.log_frame, height=6, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=False, padx=8, pady=8)

        self.on_mode_changed()

    def on_mode_changed(self) -> None:
        if self._is_scanning or self._is_creating:
            return
        for frame in (self.auto_frame, self.project_frame, self.mp4_frame):
            frame.pack_forget()
        mode = SourceMode(self.mode_var.get())
        if mode == SourceMode.AUTO:
            self.auto_frame.pack(fill=tk.X)
        elif mode == SourceMode.PROJECT:
            self.project_frame.pack(fill=tk.X)
        else:
            self.mp4_frame.pack(fill=tk.X)
        self.mode_help_var.set(MODE_HELP_TEXT[mode])
        self.clear_candidates()

    def refresh_environment(self) -> None:
        try:
            info = self.env.detect()
            self.draft_dir_var.set(str(info.draft_dir))
            process_status = self.process.status().value
            self.process_var.set(PROCESS_LABELS.get(process_status, process_status))
            self._set_badge(self.process_badge, self._process_tone(process_status))
        except Exception as exc:
            self.draft_dir_var.set("-")
            self.process_var.set("未检测到")
            self._set_badge(self.process_badge, "error")
            self.append_log(f"环境检测失败: {safe_error_message(exc)}")

    def choose_project(self) -> None:
        path = filedialog.askdirectory(title="选择剪映项目目录")
        if path:
            self.project_path_var.set(path)
            self.scan_current_source()

    def choose_mp4(self) -> None:
        path = filedialog.askopenfilename(title="选择 MP4", filetypes=[("MP4", "*.mp4"), ("All files", "*.*")])
        if path:
            self.mp4_path_var.set(path)
            if not self.source_name_var.get().strip():
                self.source_name_var.set(Path(path).stem)
            self.scan_current_source()

    def append_log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)

    def clear_candidates(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.candidates = []
        self._candidate_by_iid = {}
        self.source = None
        self.source_var.set("-")
        self.selected_var.set(candidate_summary(None))
        self.selected_path_var.set("-")
        self.empty_var.set("")
        self.create_button.configure(state=tk.DISABLED)

    def current_request(self, *, selected_media_path: Path | None = None) -> CreateDraftRequest:
        mode = SourceMode(self.mode_var.get())
        project_path = Path(self.project_path_var.get()) if self.project_path_var.get().strip() else None
        mp4_path = Path(self.mp4_path_var.get()) if self.mp4_path_var.get().strip() else None
        return build_request(
            mode,
            project_path=project_path,
            mp4_path=mp4_path,
            source_name=self.source_name_var.get().strip() or None,
            selected_media_path=selected_media_path,
        )

    def scan_current_source(self) -> None:
        if self._is_scanning or self._is_creating:
            return
        self.refresh_environment()
        self.clear_candidates()
        self.created = None
        self.phase_var.set("检测中")
        self._set_badge(self.phase_badge, "busy")
        self.status_var.set("正在检测缓存视频...")
        self.created_var.set("")
        self.result_name_var.set("-")
        self.result_path_var.set("-")
        self.result_verify_var.set("-")
        self.open_button.configure(state=tk.DISABLED)
        self.confirm_button.configure(state=tk.DISABLED)
        self._set_busy("scan")

        try:
            request = self.current_request()
        except Exception as exc:
            self._scan_failed(exc)
            return

        def worker() -> None:
            try:
                info = self.env.detect()
                source = scan_source(request, draft_root=info.draft_dir, env=self.env, process=self.process)
            except Exception as exc:
                self._post_ui(lambda exc=exc: self._scan_failed(exc))
                return
            self._post_ui(lambda source=source: self._scan_done(source))

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self, source: ResolvedSource) -> None:
        self.source = source
        self.candidates = sort_candidates_for_display(source.candidates)
        self.source_var.set(source.source_name)
        if source.mode != SourceMode.MP4 or not self.source_name_var.get().strip():
            self.source_name_var.set(source.source_name)
        self.last_scan_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for index, candidate in enumerate(self.candidates):
            iid = str(index)
            self._candidate_by_iid[iid] = candidate
            self.tree.insert("", tk.END, iid=iid, values=candidate_row(candidate), tags=(candidate_tag(candidate),))
        available = [candidate for candidate in self.candidates if candidate.status == CandidateStatus.AVAILABLE]
        if available:
            first_available = self.candidates.index(available[0])
            self.tree.selection_set(str(first_available))
            self.tree.focus(str(first_available))
            self.tree.see(str(first_available))
            self.on_candidate_selected()
            self.create_button.configure(state=tk.NORMAL)
            self.phase_var.set("可创建")
            self._set_badge(self.phase_badge, "ok")
            self.status_var.set(status_label("detected"))
            self.empty_var.set("")
        else:
            self.create_button.configure(state=tk.DISABLED)
            message = empty_state_message(self.mode_var.get(), self.candidates)
            self.phase_var.set("未找到")
            self._set_badge(self.phase_badge, "muted")
            self.status_var.set("没有可创建草稿的候选视频。")
            self.empty_var.set(message)
            self.selected_var.set(candidate_summary(None))
            self.selected_path_var.set("-")
        self._set_busy(None)
        self.append_log(f"已检测: {source.source_name}; 可用 {len(available)} / 总数 {len(self.candidates)}")

    def _scan_failed(self, exc: Exception) -> None:
        self._set_busy(None)
        self.create_button.configure(state=tk.DISABLED)
        process_status = self.process.status().value
        self.process_var.set(PROCESS_LABELS.get(process_status, process_status))
        self._set_badge(self.process_badge, self._process_tone(process_status))
        message = (
            empty_state_message(self.mode_var.get(), error_code=exc.code, process_status=process_status)
            if isinstance(exc, WorkflowError)
            else safe_error_message(exc)
        )
        self.phase_var.set("失败")
        self._set_badge(self.phase_badge, "error")
        self.status_var.set("检测失败。")
        self.empty_var.set(message)
        self.selected_var.set(candidate_summary(None))
        self.selected_path_var.set("-")
        self.append_log(f"检测失败: {message}")

    def selected_candidate(self) -> MediaCandidate | None:
        selection = self.tree.selection()
        if selection:
            candidate = self._candidate_by_iid[selection[0]]
            return candidate if candidate.status == CandidateStatus.AVAILABLE else None
        if self.source and self.source.available_candidates:
            return self.source.available_candidates[0]
        return None

    def on_candidate_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self.selected_var.set(candidate_summary(None))
            self.selected_path_var.set("-")
            self.create_button.configure(state=tk.DISABLED)
            return
        candidate = self._candidate_by_iid[selection[0]]
        self.selected_var.set(candidate_summary(candidate))
        self.selected_path_var.set(f"路径：{candidate.path}")
        self.create_button.configure(state=tk.NORMAL if candidate.status == CandidateStatus.AVAILABLE else tk.DISABLED)

    def create_selected(self) -> None:
        candidate = self.selected_candidate()
        if candidate is None:
            messagebox.showwarning("未选择视频", "请先选择一个可用视频。")
            return

        self._set_busy("create")
        self.phase_var.set("创建中")
        self._set_badge(self.phase_badge, "busy")
        self.status_var.set(status_label("creating"))
        self.empty_var.set("")
        self.append_log(f"开始创建草稿: {candidate.path}")
        request = self.current_request(selected_media_path=candidate.path)

        def worker() -> None:
            try:
                info = self.env.detect()
                result = create_draft_from_source(request, draft_root=info.draft_dir, env=self.env, process=self.process)
            except Exception as exc:
                self._post_ui(lambda exc=exc: self._create_failed(exc))
                return
            self._post_ui(lambda result=result: self._create_done(result.created_draft))

        threading.Thread(target=worker, daemon=True).start()

    def _create_done(self, created: CreatedDraft | None) -> None:
        if created is None:
            self._create_failed(RuntimeError("草稿创建结果为空"))
            return
        self.created = created
        self._set_busy(None)
        self.create_button.configure(state=tk.NORMAL)
        self.open_button.configure(state=tk.NORMAL)
        self.confirm_button.configure(state=tk.NORMAL)
        self.phase_var.set("已创建")
        self._set_badge(self.phase_badge, "ok")
        self.status_var.set(status_label("draft_created"))
        self.created_var.set(f"{status_label('draft_created')} 请在剪映首页查找并确认。")
        self.result_name_var.set(created.name)
        self.result_path_var.set(str(created.draft_path))
        self.result_verify_var.set("大小一致" if created.size_verified else "请检查")
        self.append_log(f"草稿已创建，请回到剪映首页查看: {created.draft_path}")

    def _create_failed(self, exc: Exception) -> None:
        self._set_busy(None)
        self.create_button.configure(state=tk.NORMAL if self.selected_candidate() else tk.DISABLED)
        message = safe_error_message(exc)
        self.phase_var.set("失败")
        self._set_badge(self.phase_badge, "error")
        self.status_var.set(status_label("failed"))
        self.empty_var.set(message)
        self.append_log(f"创建失败: {message}")
        messagebox.showerror("创建失败", message)

    def open_created_dir(self) -> None:
        if self.created:
            try:
                os.startfile(str(self.created.draft_path))
            except Exception as exc:
                message = safe_error_message(exc)
                self.status_var.set(status_label("failed"))
                self.append_log(f"打开草稿目录失败: {message}")
                messagebox.showerror("打开失败", message)

    def confirm_user_verified(self) -> None:
        if self.created:
            self.phase_var.set("已确认")
            self._set_badge(self.phase_badge, "ok")
            self.status_var.set(status_label("user_verified_openable"))
            self.append_log(status_label("user_verified_openable"))

    def _set_busy(self, phase: str | None) -> None:
        self._is_scanning = phase == "scan"
        self._is_creating = phase == "create"
        busy = phase is not None
        self.scan_button.configure(text="检测中..." if phase == "scan" else "重新检测")
        self.create_button.configure(text="创建中..." if phase == "create" else "创建剪映草稿")
        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()

        state = tk.DISABLED if busy else tk.NORMAL
        self.scan_button.configure(state=state)
        for button in self.mode_buttons:
            button.configure(state=state)
        for widget in (
            self.project_entry,
            self.project_button,
            self.mp4_entry,
            self.mp4_button,
            self.output_name_entry,
        ):
            widget.configure(state=state)

        if busy:
            self.create_button.configure(state=tk.DISABLED)
            self.open_button.configure(state=tk.DISABLED)
            self.confirm_button.configure(state=tk.DISABLED)
        elif self.selected_candidate():
            self.create_button.configure(state=tk.NORMAL)

    def _post_ui(self, callback) -> None:
        self._ui_events.put(callback)

    def _drain_ui_events(self) -> None:
        while True:
            try:
                callback = self._ui_events.get_nowait()
            except queue.Empty:
                break
            callback()
        self.after(50, self._drain_ui_events)

    def toggle_log(self) -> None:
        if self.log_visible_var.get():
            self.log_frame.pack_forget()
            self.log_visible_var.set(False)
            self.log_toggle_button.configure(text="显示诊断日志")
        else:
            self.log_frame.pack(fill=tk.BOTH, expand=False, pady=(6, 0))
            self.log_visible_var.set(True)
            self.log_toggle_button.configure(text="隐藏诊断日志")

    def _set_badge(self, label: tk.Label, tone: str) -> None:
        foreground, background = STATUS_COLORS.get(tone, STATUS_COLORS["muted"])
        label.configure(foreground=foreground, background=background)

    def _process_tone(self, process_status: str) -> str:
        if process_status == "running":
            return "ok"
        if process_status in {"starting", "background", "tray_only"}:
            return "busy"
        if process_status == "not_installed":
            return "error"
        return "muted"


def main() -> None:
    app = CacheExtractorApp()
    app.mainloop()
