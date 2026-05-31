"""Tkinter GUI for the JianYing cache extraction workflow."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .auto_import import auto_import_file
from .cache_extractor import find_combination_mp4s, scan_latest_cache
from .compound_clip import DEFAULT_PRECOMPOSE_HOTKEY, run_compound_clip_sequence, run_uncompose_clip_sequence
from .draft_creator import create_extracted_draft
from .draft_detector import detect_recent_drafts
from .env import JianYingEnv
from .models import DraftFolder, MediaCandidate, ProcessStatus, WorkflowPhase
from .private_cache_draft import create_private_cache_draft
from .private_cache_scan import inspect_private_cache
from .process import JianYingProcess

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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
}

# Usage instructions shown to the user
USAGE_INSTRUCTIONS = """\
本工具通过剪映的「复合片段预合成」机制提取视频缓存，绕过 VIP 导出限制。

⚠️ 使用前必须设置快捷键：
  剪映菜单 → 设置 → 快捷键 → 恢复默认 → 找到「预合成复合片段（子草稿）」→ 设为自定义快捷键（默认 Shift+G）

📋 使用流程：
  ① 在剪映中打开项目，将素材拖入时间线
  ② 勾选「我已打开该项目编辑界面」
  ③ 点击「一键复合片段」→ 等待渲染完成（缓存视频列表自动刷新）
  ④ 点击「重启剪映」→ 等待剪映重新启动
  ⑤ 重新打开同一项目，勾选「我已打开该项目编辑界面」
  ⑥ 点击「一键导入」→ 缓存视频将导入到时间线

💡 提示：
  - 每步操作只发送请求，不保证成功，请观察剪映的实际反馈
  - 草稿名自动从缓存文件名生成，可直接点击「创建剪映草稿」保存为独立草稿"""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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
        return "✓ 可导入"
    if phase == WorkflowPhase.COMPOSITE_DONE:
        return "等待重启剪映"
    return "✓ 格式正确"


def _classification_tag(status: str, phase: WorkflowPhase = WorkflowPhase.IDLE) -> str:
    if status not in ("standard_importable", "private_importable"):
        return "rejected"
    if phase in (WorkflowPhase.RESTARTED, WorkflowPhase.IMPORTED):
        return "available"
    if phase == WorkflowPhase.COMPOSITE_DONE:
        return "writing"
    return "available"


def _badge_style(tone: str) -> dict:
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


# ---------------------------------------------------------------------------
# HotkeyCapture widget
# ---------------------------------------------------------------------------

_MASK_SHIFT = 0x1
_MASK_CONTROL = 0x4
_MASK_ALT = 0x20000
_MODIFIER_KEYSYMS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}


class HotkeyCapture(tk.Frame):
    def __init__(self, parent: tk.Widget, initial: str = DEFAULT_PRECOMPOSE_HOTKEY, **kwargs):
        super().__init__(parent, **kwargs)
        self._internal: str = initial
        self._display: str = self._format_display(initial)
        self._capturing = False

        self.entry = tk.Entry(self, width=16, font=("", 10), justify="center")
        self.entry.pack(fill="x")
        self.entry.insert(0, self._display)
        self.entry.config(state="readonly")
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<KeyPress>", self._on_key_press)
        self.entry.bind("<Escape>", self._on_escape)
        self.entry.bind("<BackSpace>", self._on_backspace)

    def get_internal(self) -> str:
        return self._internal

    def _on_focus_in(self, _event: tk.Event) -> None:
        self._capturing = True
        self.entry.config(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, "请按下快捷键...")
        self.entry.config(fg="#6b7280", font=("", 10, "italic"))

    def _on_focus_out(self, _event: tk.Event) -> None:
        if self._capturing:
            self._capturing = False
            self._show_current()

    def _on_key_press(self, event: tk.Event) -> None:
        keysym = event.keysym
        if keysym in _MODIFIER_KEYSYMS:
            return
        parts_internal: list[str] = []
        parts_display: list[str] = []
        if event.state & _MASK_SHIFT:
            parts_internal.append("shift")
            parts_display.append("Shift")
        if event.state & _MASK_CONTROL:
            parts_internal.append("ctrl")
            parts_display.append("Ctrl")
        if event.state & _MASK_ALT:
            parts_internal.append("alt")
            parts_display.append("Alt")
        key = keysym
        if len(key) == 1:
            key = key.lower()
        elif key.startswith("KP_"):
            key = key[3:]
        if not parts_display:
            return
        parts_internal.append(key)
        parts_display.append(key.upper() if len(key) == 1 else key)
        self._internal = "+".join(parts_internal)
        self._display = " + ".join(parts_display)
        self._capturing = False
        self._show_current()
        self.entry.master.focus_set()
        return "break"

    def _on_escape(self, _event: tk.Event) -> None:
        self._capturing = False
        self._show_current()
        self.entry.master.focus_set()
        return "break"

    def _on_backspace(self, _event: tk.Event) -> None:
        self._internal = DEFAULT_PRECOMPOSE_HOTKEY
        self._display = self._format_display(DEFAULT_PRECOMPOSE_HOTKEY)
        self._capturing = False
        self._show_current()
        return "break"

    def _show_current(self) -> None:
        self.entry.config(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, self._display)
        self.entry.config(state="readonly", fg="#111827", font=("", 10, "bold"))

    @staticmethod
    def _format_display(internal: str) -> str:
        parts = internal.split("+")
        display_parts: list[str] = []
        for p in parts:
            if p in ("shift", "ctrl", "alt"):
                display_parts.append(p.capitalize())
            elif len(p) == 1:
                display_parts.append(p.upper())
            else:
                display_parts.append(p)
        return " + ".join(display_parts)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class GuiState:
    selected_project_path: Path | None = None
    opened_project_confirmed: bool = False
    tracked_mp4_path: Path | None = None
    process_status: ProcessStatus = ProcessStatus.STOPPED
    workflow_phase: WorkflowPhase = WorkflowPhase.IDLE
    busy: bool = False


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


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class JianYingApp:
    def __init__(self) -> None:
        import ttkbootstrap as tb

        self.tb = tb
        self.root = tb.Window(themename="darkly")
        self.root.title(APP_TITLE)
        self.root.geometry("1100x900")
        self.root.minsize(1000, 780)

        self.env = JianYingEnv()
        self.process = JianYingProcess(self.env)
        self.state = GuiState()
        self.drafts: list[DraftFolder] = []
        self._candidate_by_iid: dict[str, MediaCandidate] = {}
        self.created_draft_path: Path | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        # Tk variables
        self.status_var = tk.StringVar(value="正在检测环境...")
        self.process_var = tk.StringVar(value="-")
        self.version_var = tk.StringVar(value="-")
        self.draft_dir_var = tk.StringVar(value="-")
        self.phase_var = tk.StringVar(value="准备中")
        self.tracked_var = tk.StringVar(value="")
        self.draft_name_var = tk.StringVar(value="")
        self.created_name_var = tk.StringVar(value="-")
        self.created_path_var = tk.StringVar(value="-")
        self.selected_var = tk.StringVar(value="")

        self._build()
        self._apply_button_states()
        self.after(50, self._drain_events)
        self.after(100, self._refresh_environment_and_projects)
        self.after(300, self._refresh_process_status)

    def after(self, ms: int, func: Callable[..., None]) -> None:
        self.root.after(ms, func)

    def run(self) -> None:
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        tb = self.tb
        root_frame = tb.Frame(self.root, padding=12)
        root_frame.pack(fill="both", expand=True)

        # ── Header bar ──
        header = tb.Frame(root_frame)
        header.pack(fill="x", pady=(0, 8))
        tb.Label(header, text="剪映缓存提取工具", font=("", 16, "bold"), bootstyle="inverse-primary").pack(side="left")
        tb.Label(header, text=APP_VERSION, font=("", 10), bootstyle="secondary").pack(side="left", padx=(8, 0), pady=(4, 0))
        self.help_toggle = tb.Button(
            header, text="使用说明 ▼", command=self._toggle_help,
            bootstyle="secondary-outline", width=12,
        )
        self.help_toggle.pack(side="right")

        # ── Help / instructions (collapsible, default open) ──
        self.help_visible = True
        self.help_frame = tb.Frame(root_frame)
        self.help_frame.pack(fill="x", pady=(0, 8))
        help_text = tk.Text(
            self.help_frame, height=10, wrap="word", font=("", 10),
            background="#1a1a2e", foreground="#c8c8d4", relief="flat",
            padx=12, pady=8, borderwidth=0,
        )
        help_text.insert("1.0", USAGE_INSTRUCTIONS)
        help_text.config(state="disabled")
        help_text.pack(fill="x")

        # ── Environment info ──
        env_frame = tb.Labelframe(root_frame, text=" 环境信息 ", padding=8)
        env_frame.pack(fill="x", pady=(0, 6))
        env_frame.columnconfigure(1, weight=1)
        env_frame.columnconfigure(3, weight=1)

        tb.Label(env_frame, text="剪映状态").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.process_badge = tk.Label(
            env_frame, textvariable=self.process_var,
            padx=8, pady=2, font=("", 9, "bold"), relief="groove", bd=1,
        )
        self.process_badge.grid(row=0, column=1, sticky="w")
        tb.Label(env_frame, text="版本").grid(row=0, column=2, sticky="w", padx=(16, 6))
        tb.Label(env_frame, textvariable=self.version_var).grid(row=0, column=3, sticky="w")
        tb.Label(env_frame, text="草稿目录").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        tb.Label(env_frame, textvariable=self.draft_dir_var, bootstyle="secondary").grid(
            row=1, column=1, columnspan=3, sticky="ew", pady=(4, 0),
        )

        # ── Project selection ──
        proj_frame = tb.Labelframe(root_frame, text=" 项目选择 ", padding=8)
        proj_frame.pack(fill="x", pady=(0, 6))

        combo_row = tb.Frame(proj_frame)
        combo_row.pack(fill="x")
        combo_row.columnconfigure(0, weight=1)
        self.project_combo = tb.Combobox(
            combo_row, textvariable=tk.StringVar(), state="readonly"
        )
        self.project_combo.grid(row=0, column=0, sticky="ew")
        self.project_combo.bind("<<ComboboxSelected>>", lambda _: self._on_project_selected())
        tb.Button(combo_row, text="重新检测", command=self._refresh_projects, bootstyle="secondary-outline").grid(
            row=0, column=1, padx=(8, 0),
        )

        self.confirm_var = tk.BooleanVar(value=False)
        tb.Checkbutton(
            proj_frame, text="我已打开该项目编辑界面",
            variable=self.confirm_var, command=self._on_confirm_changed,
        ).pack(anchor="w", pady=(6, 0))

        # ── Cache video list ──
        cand_frame = tb.Labelframe(root_frame, text=" 缓存视频 ", padding=8)
        cand_frame.pack(fill="both", expand=True, pady=(0, 6))

        columns = ("name", "size", "resolution", "duration", "status")
        tree_area = tb.Frame(cand_frame)
        tree_area.pack(fill="both", expand=True)

        self.tree = tb.Treeview(tree_area, columns=columns, show="headings", height=4, bootstyle="primary")
        self.tree.tag_configure("available", foreground="#22c55e")
        self.tree.tag_configure("writing", foreground="#f59e0b")
        self.tree.tag_configure("rejected", foreground="#94a3b8")

        headings = {"name": "缓存文件", "size": "大小", "resolution": "分辨率", "duration": "时长", "status": "状态"}
        widths = {"name": 300, "size": 90, "resolution": 110, "duration": 90, "status": 140}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], minwidth=20, stretch=(col == "name"))
        scrollbar = tb.Scrollbar(tree_area, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_candidate_selected)

        self.selected_label = tb.Label(cand_frame, textvariable=self.selected_var, bootstyle="secondary")
        self.selected_label.pack(fill="x", pady=(6, 0))

        # ── Three-step actions ──
        act_frame = tb.Labelframe(root_frame, text=" 三步操作 ", padding=8)
        act_frame.pack(fill="x", pady=(0, 6))
        act_frame.columnconfigure(1, weight=1)
        act_frame.columnconfigure(5, weight=1)

        # Row 0: draft name + scan + create
        tb.Label(act_frame, text="草稿名").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 4))
        tb.Entry(act_frame, textvariable=self.draft_name_var).grid(row=0, column=1, sticky="ew", pady=(0, 4))
        self.scan_btn = tb.Button(act_frame, text="扫描缓存", command=self._on_scan, bootstyle="primary-outline", width=10)
        self.scan_btn.grid(row=0, column=2, padx=(8, 0), pady=(0, 4))
        self.create_btn = tb.Button(act_frame, text="创建剪映草稿", command=self._on_create_draft, bootstyle="success", width=12, state="disabled")
        self.create_btn.grid(row=0, column=3, padx=(8, 0), pady=(0, 4))

        # Row 1: hotkey + compound + uncompose
        tb.Label(act_frame, text="快捷键").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 4))
        self.hotkey_capture = HotkeyCapture(act_frame)
        self.hotkey_capture.grid(row=1, column=1, sticky="w", pady=(4, 4))
        self.compound_btn = tb.Button(act_frame, text="① 一键复合片段", command=self._on_compound, bootstyle="info-outline", width=14, state="disabled")
        self.compound_btn.grid(row=1, column=2, padx=(8, 0), pady=(4, 4))
        self.uncompose_btn = tb.Button(act_frame, text="解除复合片段", command=self._on_uncompose, bootstyle="secondary-outline", width=10, state="disabled")
        self.uncompose_btn.grid(row=1, column=3, padx=(8, 0), pady=(4, 4))

        # Row 2: phase badge + restart + import + tracked
        self.phase_badge = tk.Label(
            act_frame, textvariable=self.phase_var,
            padx=8, pady=2, font=("", 9, "bold"), relief="groove", bd=1,
        )
        self.phase_badge.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.restart_btn = tb.Button(act_frame, text="② 重启剪映", command=self._on_restart, bootstyle="warning-outline", width=12, state="disabled")
        self.restart_btn.grid(row=2, column=2, padx=(8, 0), pady=(4, 0))
        self.import_btn = tb.Button(act_frame, text="③ 一键导入", command=self._on_import, bootstyle="success", width=10, state="disabled")
        self.import_btn.grid(row=2, column=3, padx=(8, 0), pady=(4, 0))
        self.tracked_label = tb.Label(act_frame, textvariable=self.tracked_var, bootstyle="secondary", font=("", 9))
        self.tracked_label.grid(row=2, column=4, columnspan=2, sticky="w", padx=(8, 0), pady=(4, 0))

        # ── Result ──
        res_frame = tb.Labelframe(root_frame, text=" 创建结果 ", padding=8)
        res_frame.pack(fill="x", pady=(0, 6))
        res_frame.columnconfigure(1, weight=1)

        self.result_var = tk.StringVar(value="")
        tb.Label(res_frame, textvariable=self.result_var, font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 4),
        )
        tb.Label(res_frame, text="草稿名").grid(row=1, column=0, sticky="w", padx=(0, 6))
        tb.Label(res_frame, textvariable=self.created_name_var).grid(row=1, column=1, sticky="w")
        tb.Label(res_frame, text="草稿路径").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        tb.Label(res_frame, textvariable=self.created_path_var).grid(
            row=2, column=1, columnspan=3, sticky="ew", pady=(4, 0),
        )

        btn_row = tb.Frame(res_frame)
        btn_row.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.open_dir_btn = tb.Button(
            btn_row, text="打开草稿目录", command=self._open_created_dir,
            bootstyle="secondary-outline", state="disabled",
        )
        self.open_dir_btn.pack(side="left", padx=(0, 8))

        # ── Diagnostics log (collapsible) ──
        log_toggle_row = tb.Frame(root_frame)
        log_toggle_row.pack(fill="x")
        self.log_visible = False
        self.log_toggle_btn = tb.Button(
            log_toggle_row, text="▶ 诊断日志", command=self._toggle_log,
            bootstyle="secondary-outline",
        )
        self.log_toggle_btn.pack(side="left")

        self.log_frame = tb.Labelframe(root_frame, text=" 诊断日志 ", padding=4)
        self.log_text = tk.Text(self.log_frame, height=5, wrap="word", font=("Consolas", 9))

    # ------------------------------------------------------------------
    # Help toggle
    # ------------------------------------------------------------------

    def _toggle_help(self) -> None:
        if self.help_visible:
            self.help_frame.pack_forget()
            self.help_toggle.configure(text="使用说明 ▼")
            self.help_visible = False
        else:
            self.help_frame.pack(fill="x", pady=(0, 8), after=self.root.winfo_children()[0])
            self.help_toggle.configure(text="使用说明 ▲")
            self.help_visible = True

    # ------------------------------------------------------------------
    # Log toggle
    # ------------------------------------------------------------------

    def _toggle_log(self) -> None:
        if self.log_visible:
            self.log_text.pack_forget()
            self.log_frame.pack_forget()
            self.log_toggle_btn.configure(text="▶ 诊断日志")
            self.log_visible = False
        else:
            self.log_frame.pack(fill="x", pady=(4, 0))
            self.log_text.pack(fill="both")
            self.log_toggle_btn.configure(text="▼ 诊断日志")
            self.log_visible = True

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        if not self.log_visible:
            self._toggle_log()

    # ------------------------------------------------------------------
    # Badge updates
    # ------------------------------------------------------------------

    def _update_process_badge(self) -> None:
        label = PROCESS_LABELS.get(self.state.process_status.value, self.state.process_status.value)
        self.process_var.set(label)
        style = _badge_style(_process_tone(self.state.process_status))
        self.process_badge.configure(**style)

    def _update_phase_badge(self) -> None:
        label = PHASE_LABELS.get(self.state.workflow_phase, "准备中")
        self.phase_var.set(label)
        style = _badge_style(_phase_tone(self.state.workflow_phase))
        self.phase_badge.configure(**style)

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------

    def _populate_tree(self, files: list) -> None:
        self.tree.delete(*self.tree.get_children())
        self._candidate_by_iid.clear()

        for f in files:
            path = f if isinstance(f, Path) else getattr(f, "path", None)
            if path is None:
                continue

            inspection = inspect_private_cache(path)
            display_text = _classification_display(inspection.status, inspection.reason, self.state.workflow_phase)
            tag = _classification_tag(inspection.status, self.state.workflow_phase)

            iid = self.tree.insert("", "end", values=(
                path.name,
                human_size(inspection.size_bytes),
                resolution_label(inspection.width, inspection.height),
                human_duration(inspection.duration_ms),
                display_text,
            ), tags=(tag,))
            self._candidate_by_iid[iid] = inspection

    def _on_candidate_selected(self, _event: tk.Event | None = None) -> None:
        sel = self.tree.selection()
        if not sel:
            self.selected_var.set("")
            return
        item = sel[0]
        values = self.tree.item(item, "values")
        if values:
            name = values[0]
            size = values[1]
            res = values[2]
            dur = values[3]
            self.selected_var.set(f"已选择: {name}  ({size}, {res}, {dur})")
        else:
            self.selected_var.set("")

    # ------------------------------------------------------------------
    # Environment & process
    # ------------------------------------------------------------------

    def _refresh_environment_and_projects(self) -> None:
        def work() -> None:
            try:
                self.env.detect()
                info = self.env.info
                self.events.put(("env", info))
                drafts = detect_recent_drafts(info.draft_dir)
                self.events.put(("projects", drafts))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self._run_background(work)

    def _refresh_projects(self) -> None:
        def work() -> None:
            try:
                info = self.env.info
                drafts = detect_recent_drafts(info.draft_dir)
                self.events.put(("projects", drafts))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self._run_background(work)

    def _refresh_process_status(self) -> None:
        try:
            self.state.process_status = self.process.status()
            self._update_process_badge()
            self._apply_button_states()
        finally:
            self.root.after(3000, self._refresh_process_status)

    # ------------------------------------------------------------------
    # UI event handlers
    # ------------------------------------------------------------------

    def _on_project_selected(self) -> None:
        index = self.project_combo.current()
        if 0 <= index < len(self.drafts):
            self.state.selected_project_path = self.drafts[index].path
            self.state.tracked_mp4_path = None
            self.state.workflow_phase = WorkflowPhase.IDLE
            self.tracked_var.set("")
            self._update_phase_badge()
            self._log(f"已选择项目: {self.drafts[index].name}")
            self._on_scan()
        self._apply_button_states()

    def _on_confirm_changed(self) -> None:
        self.state.opened_project_confirmed = bool(self.confirm_var.get())
        self._apply_button_states()

    def _on_scan(self) -> None:
        project = self.state.selected_project_path
        if project is None:
            return

        def work() -> None:
            files = find_combination_mp4s(project, require_video=False, recent_seconds=None)
            self.events.put(("scan", files))

        self._log("正在扫描缓存文件...")
        self._run_background(work)

    def _on_compound(self) -> None:
        project = self.state.selected_project_path
        if project is None:
            return
        hotkey = self.hotkey_capture.get_internal()

        def work() -> None:
            result = run_compound_clip_sequence(hotkey)
            latest = scan_latest_cache(project, require_video=False)
            self.events.put(("compound", (result, latest)))

        self._run_background(work)

    def _on_uncompose(self) -> None:
        self._run_background(lambda: self.events.put(("uncompose", run_uncompose_clip_sequence())))

    def _on_restart(self) -> None:
        from .private_prepare import restart_jianying_for_import

        def work() -> None:
            self.events.put(("restart", restart_jianying_for_import(process=self.process)))

        self._run_background(work)

    def _on_import(self) -> None:
        path = self.state.tracked_mp4_path
        if path is None:
            return
        self._run_background(lambda: self.events.put(("import", auto_import_file(path))))

    def _on_create_draft(self) -> None:
        path = self.state.tracked_mp4_path
        if path is None:
            return
        name = self.draft_name_var.get() or path.stem

        def work() -> None:
            inspection = inspect_private_cache(path)
            if inspection.status == "private_importable":
                created = create_private_cache_draft(self.env.info.draft_dir, path, name)
            else:
                created = create_extracted_draft(self.env.info.draft_dir, path, name)
            self.events.put(("created", created.draft_path))

        self._run_background(work)

    def _open_created_dir(self) -> None:
        if self.created_draft_path and self.created_draft_path.exists():
            import subprocess
            subprocess.Popen(["explorer", str(self.created_draft_path)])

    # ------------------------------------------------------------------
    # Threading
    # ------------------------------------------------------------------

    def _run_background(self, target: Callable[[], None]) -> None:
        if self.state.busy:
            return
        self.state.busy = True
        self._apply_button_states()

        def wrapped() -> None:
            try:
                target()
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("idle", None))

        threading.Thread(target=wrapped, daemon=True).start()

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event, payload)
        self.root.after(50, self._drain_events)

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    def _handle_event(self, event: str, payload: object) -> None:
        if event == "idle":
            self.state.busy = False

        elif event == "env":
            info = payload
            self.version_var.set(getattr(info, "version", "-") or "-")
            self.draft_dir_var.set(str(getattr(info, "draft_dir", "-")))
            self._log(f"环境检测完成: {getattr(info, 'version', 'unknown')}")

        elif event == "projects":
            self.drafts = list(payload)  # type: ignore[arg-type]
            self.project_combo["values"] = [d.name for d in self.drafts]
            self._log(f"检测到 {len(self.drafts)} 个近 30 分钟项目。")
            if self.drafts:
                self.project_combo.current(0)
                self._on_project_selected()

        elif event == "scan":
            files = payload
            if isinstance(files, list):
                self._populate_tree(files)
                if files:
                    latest = files[0]
                    path = latest if isinstance(latest, Path) else getattr(latest, "path", None)
                    if path:
                        self._set_tracked(path)
                        if not self.draft_name_var.get():
                            stem = path.stem.replace("_video", "")
                            self.draft_name_var.set(stem)
                    self._log(f"扫描到 {len(files)} 个缓存文件。")
                else:
                    self._set_tracked(None)
                    self._log("未找到缓存文件。")
            else:
                self._set_tracked(payload if isinstance(payload, Path) else None)

        elif event == "compound":
            result, latest = payload  # type: ignore[misc]
            self._log(format_status_message("compound_sent", None))
            if getattr(result, "status", "") == "sent":
                self.state.workflow_phase = WorkflowPhase.COMPOSITE_DONE
                self._update_phase_badge()
            self._set_tracked(latest if isinstance(latest, Path) else None)

        elif event == "uncompose":
            self._log("已发送解除复合请求")

        elif event == "restart":
            result = payload
            if getattr(result, "status", "") == "ready_for_manual_import":
                self.state.workflow_phase = WorkflowPhase.RESTARTED
                self.state.opened_project_confirmed = False
                self.confirm_var.set(False)
                self._update_phase_badge()
                self._log(format_status_message("restart_ready", None))
                self._on_scan()
            else:
                warnings = getattr(result, "warnings", [])
                self._log(f"操作失败: {warnings[0] if warnings else '重启失败'}")

        elif event == "import":
            result = payload
            if getattr(result, "status", "") == "sent":
                self.state.workflow_phase = WorkflowPhase.IMPORTED
                self._update_phase_badge()
                self._log(format_status_message("import_sent", None))
            else:
                detail = getattr(result, "error_detail", "导入失败")
                self._log(f"操作失败: {detail}")

        elif event == "created":
            path = payload
            if isinstance(path, Path):
                self.created_draft_path = path
                self.result_var.set("✓ 草稿创建成功")
                self.created_name_var.set(path.name)
                self.created_path_var.set(str(path))
                self.open_dir_btn.configure(state="normal")
                self._log(f"已创建草稿: {path}")

        elif event == "error":
            self._log(f"操作失败: {payload}")

        self._apply_button_states()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_tracked(self, path: Path | None) -> None:
        self.state.tracked_mp4_path = path
        if path is None:
            self.tracked_var.set("")
            return
        size = human_size(path.stat().st_size) if path.exists() else "?"
        self.tracked_var.set(f"追踪: {path.name} ({size})")
        self._log(format_status_message("cache_found", f"{path.name} ({size})"))

    def _apply_button_states(self) -> None:
        states = button_states(
            process=self.state.process_status,
            phase=self.state.workflow_phase,
            selected_project=self.state.selected_project_path is not None,
            confirmed_open=self.state.opened_project_confirmed,
            tracked_mp4=self.state.tracked_mp4_path is not None,
            busy=self.state.busy,
        )
        mapping = {
            "scan": getattr(self, "scan_btn", None),
            "create_draft": getattr(self, "create_btn", None),
            "compound": getattr(self, "compound_btn", None),
            "restart": getattr(self, "restart_btn", None),
            "auto_import": getattr(self, "import_btn", None),
            "uncompose": getattr(self, "uncompose_btn", None),
        }
        for key, button in mapping.items():
            if button is not None:
                button.configure(state="normal" if states[key] else "disabled")


def main() -> None:
    app = JianYingApp()
    app.run()
