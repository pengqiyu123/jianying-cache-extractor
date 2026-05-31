"""pywebview API bridge for the JianYing desktop UI."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ..auto_import import auto_import_file
from ..cache_extractor import find_combination_mp4s, scan_latest_cache
from ..compound_clip import DEFAULT_PRECOMPOSE_HOTKEY, run_compound_clip_sequence, run_uncompose_clip_sequence
from ..draft_creator import create_extracted_draft
from ..draft_detector import detect_recent_drafts
from ..env import JianYingEnv
from ..models import DraftFolder, ProcessStatus, WorkflowPhase
from ..private_cache_draft import create_private_cache_draft
from ..private_cache_scan import PrivateCacheInspection, inspect_private_cache
from ..private_prepare import restart_jianying_for_import
from ..process import JianYingProcess
from .state import (
    GuiState,
    button_states,
    format_status_message,
    human_duration,
    human_size,
    resolution_label,
    _classification_display,
    _classification_tag,
)


class PythonApi:
    def __init__(self) -> None:
        self.env = JianYingEnv()
        self.process = JianYingProcess(self.env)
        self.state = GuiState()
        self.drafts: list[DraftFolder] = []
        self.candidates: list[Path] = []
        self.created_draft_path: Path | None = None
        self._window = None
        self._lock = threading.Lock()
        self._polling = False

    def set_window(self, window) -> None:
        self._window = window

    def detect_environment(self) -> dict[str, Any]:
        return self._run_background("detect_environment", self._detect_environment)

    def refresh_projects(self) -> dict[str, Any]:
        return self._run_background("refresh_projects", self._refresh_projects)

    def scan_cache(self) -> dict[str, Any]:
        return self._run_background("scan_cache", self._scan_cache)

    def compound_clip(self, hotkey: str = DEFAULT_PRECOMPOSE_HOTKEY) -> dict[str, Any]:
        return self._run_background("compound_clip", lambda: self._compound_clip(hotkey or DEFAULT_PRECOMPOSE_HOTKEY))

    def uncompose_clip(self) -> dict[str, Any]:
        return self._run_background("uncompose_clip", self._uncompose_clip)

    def restart_jianying(self) -> dict[str, Any]:
        return self._run_background("restart_jianying", self._restart_jianying)

    def auto_import(self) -> dict[str, Any]:
        return self._run_background("auto_import", self._auto_import)

    def create_draft(self, name: str | None = None) -> dict[str, Any]:
        return self._run_background("create_draft", lambda: self._create_draft(name))

    def select_project(self, index: int) -> dict[str, Any]:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return {"accepted": False, "error": "invalid_project_index"}
        if not (0 <= index < len(self.drafts)):
            return {"accepted": False, "error": "project_index_out_of_range"}
        draft = self.drafts[index]
        self.state.selected_project_path = draft.path
        self.state.opened_project_confirmed = False
        self.state.tracked_mp4_path = None
        self.state.workflow_phase = WorkflowPhase.IDLE
        self._emit("selection", {"projectIndex": index, "projectPath": str(draft.path), "confirmed": False})
        self._emit_button_states()
        return {"accepted": True}

    def select_media(self, index: int) -> dict[str, Any]:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return {"accepted": False, "error": "invalid_media_index"}
        if not (0 <= index < len(self.candidates)):
            return {"accepted": False, "error": "media_index_out_of_range"}
        self._set_tracked(self.candidates[index])
        self._emit_button_states()
        return {"accepted": True}

    def set_confirmed_open(self, value: bool) -> dict[str, Any]:
        self.state.opened_project_confirmed = bool(value)
        self._emit("selection", {"confirmed": self.state.opened_project_confirmed})
        self._emit_button_states()
        return {"accepted": True}

    def get_button_states(self) -> dict[str, bool]:
        return self._button_states()

    def start_process_polling(self) -> dict[str, Any]:
        """Start process status polling. Called once from the UI thread via webview.start(func=)."""
        if self._polling:
            return {"accepted": True}
        self._polling = True
        # Inject a JS setInterval that calls back into this Python API method.
        # This avoids the recursion crash caused by calling evaluate_js from a
        # background Python thread (WebView2 only allows UI-thread access).
        if self._window is not None:
            try:
                self._window.evaluate_js(
                    "setInterval(function(){ if(window.pywebview && window.pywebview.api){ window.pywebview.api.poll_process_status(); } }, 3000);"
                )
            except Exception:
                pass
        return {"accepted": True}

    def poll_process_status(self) -> dict[str, Any]:
        """Called periodically by the JS setInterval on the UI thread."""
        try:
            self.state.process_status = self.process.status()
            self._emit(
                "process_status",
                {"status": self.state.process_status.value, "label": self.state.process_status.value},
            )
            self._emit_button_states()
        except Exception as exc:
            self._emit_error("process_status_failed", str(exc))
        return {"accepted": True}

    def open_draft_dir(self) -> dict[str, Any]:
        if self.created_draft_path is None or not self.created_draft_path.exists():
            return {"accepted": False, "error": "draft_dir_missing"}
        subprocess.Popen(["explorer", str(self.created_draft_path)])
        return {"accepted": True}

    def _detect_environment(self) -> None:
        info = self.env.detect()
        self._emit(
            "env_info",
            {
                "version": info.version,
                "installDir": str(info.install_dir),
                "draftDir": str(info.draft_dir),
            },
        )
        self._refresh_projects()

    def _refresh_projects(self) -> None:
        drafts = detect_recent_drafts(self.env.info.draft_dir)
        self.drafts = drafts
        self._emit("projects", {"projects": [_draft_payload(index, draft) for index, draft in enumerate(drafts)]})

    def _scan_cache(self) -> None:
        project = self.state.selected_project_path
        if project is None:
            self._emit_error("project_required", "请先选择项目")
            return
        files = find_combination_mp4s(project, require_video=False, recent_seconds=None)
        self.candidates = [file.path for file in files]
        payloads = [_cache_payload(index, file.path, inspect_private_cache(file.path), self.state.workflow_phase) for index, file in enumerate(files)]
        self._emit("scan_result", {"files": payloads})
        if files:
            self._set_tracked(files[0].path)
        else:
            self.state.tracked_mp4_path = None
            self._emit("tracked_media", {"path": None})

    def _compound_clip(self, hotkey: str) -> None:
        if self.state.selected_project_path is None:
            self._emit_error("project_required", "请先选择项目")
            return
        if not self.state.opened_project_confirmed:
            self._emit_error("project_not_confirmed", "请先确认已打开目标项目")
            return
        result = run_compound_clip_sequence(hotkey)
        latest = scan_latest_cache(self.state.selected_project_path, require_video=False)
        if result.status == "sent":
            self.state.workflow_phase = WorkflowPhase.COMPOSITE_DONE
            if latest is not None:
                self._set_tracked(latest)
            self._emit("compound_result", {"status": result.status, "message": format_status_message("compound_sent", None)})
        else:
            self._emit("compound_result", {"status": result.status, "warnings": result.warnings})

    def _uncompose_clip(self) -> None:
        result = run_uncompose_clip_sequence()
        self._emit("uncompose_result", {"status": result.status, "warnings": result.warnings})

    def _restart_jianying(self) -> None:
        result = restart_jianying_for_import(process=self.process)
        if result.status == "ready_for_manual_import":
            self.state.workflow_phase = WorkflowPhase.RESTARTED
            self.state.opened_project_confirmed = False
            self._emit(
                "restart_result",
                {"status": result.status, "message": format_status_message("restart_ready", None), "warnings": result.warnings},
            )
        else:
            self._emit("restart_result", {"status": result.status, "warnings": result.warnings})

    def _auto_import(self) -> None:
        path = self.state.tracked_mp4_path
        if path is None:
            self._emit_error("media_required", "请先选择缓存视频")
            return
        if not self.state.opened_project_confirmed:
            self._emit_error("project_not_confirmed", "请先确认已打开目标项目")
            return
        result = auto_import_file(path)
        if result.status == "sent":
            self.state.workflow_phase = WorkflowPhase.IMPORTED
            self._emit("import_result", {"status": result.status, "message": format_status_message("import_sent", None)})
        else:
            self._emit("import_result", {"status": result.status, "error": result.error_detail})

    def _create_draft(self, name: str | None) -> None:
        path = self.state.tracked_mp4_path
        if path is None:
            self._emit_error("media_required", "请先选择缓存视频")
            return
        draft_name = name or path.stem.replace("_video", "")
        inspection = inspect_private_cache(path)
        if inspection.status == "private_importable":
            created = create_private_cache_draft(self.env.info.draft_dir, path, draft_name)
        else:
            created = create_extracted_draft(self.env.info.draft_dir, path, draft_name)
        self.created_draft_path = created.draft_path
        self._emit(
            "draft_created",
            {
                "status": "draft_created",
                "name": created.name,
                "path": str(created.draft_path),
                "mediaPath": str(created.media_path) if created.media_path else None,
                "sizeVerified": created.size_verified,
            },
        )

    def _run_background(self, action: str, target: Callable[[], None]) -> dict[str, Any]:
        with self._lock:
            if self.state.busy:
                return {"accepted": False, "error": "busy"}
            self.state.busy = True
        self._emit("action_started", {"action": action})
        self._emit_button_states()

        def wrapped() -> None:
            try:
                target()
            except Exception as exc:
                self._emit_error("unexpected_error", str(exc))
            finally:
                with self._lock:
                    self.state.busy = False
                self._emit("action_finished", {"action": action})
                self._emit_button_states()

        threading.Thread(target=wrapped, daemon=True).start()
        return {"accepted": True}

    def _set_tracked(self, path: Path | None) -> None:
        self.state.tracked_mp4_path = path
        if path is None:
            self._emit("tracked_media", {"path": None})
            return
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        self._emit(
            "tracked_media",
            {"path": str(path), "name": path.name, "size": size, "sizeText": human_size(size)},
        )

    def _button_states(self) -> dict[str, bool]:
        return button_states(
            process=self.state.process_status,
            phase=self.state.workflow_phase,
            selected_project=self.state.selected_project_path is not None,
            confirmed_open=self.state.opened_project_confirmed,
            tracked_mp4=self.state.tracked_mp4_path is not None,
            busy=self.state.busy,
        )

    def _emit_button_states(self) -> None:
        self._emit(
            "button_states",
            {
                "states": self._button_states(),
                "phase": self.state.workflow_phase.value,
                "confirmed": self.state.opened_project_confirmed,
            },
        )

    def _emit_error(self, code: str, message: str) -> None:
        self._emit("error", {"code": code, "message": message})

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._window is None:
            return
        script = "window.__onPyEvent && window.__onPyEvent(%s, %s);" % (
            json.dumps(event, ensure_ascii=False),
            json.dumps(_jsonable(payload), ensure_ascii=False),
        )
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass


def _draft_payload(index: int, draft: DraftFolder) -> dict[str, Any]:
    return {
        "index": index,
        "name": draft.name,
        "path": str(draft.path),
        "modifiedAt": draft.modified_at.isoformat(),
        "hasCombinationCache": draft.has_combination_cache,
    }


def _cache_payload(index: int, path: Path, inspection: PrivateCacheInspection, phase: WorkflowPhase) -> dict[str, Any]:
    return {
        "index": index,
        "name": path.name,
        "path": str(path),
        "size": inspection.size_bytes,
        "sizeText": human_size(inspection.size_bytes),
        "resolution": resolution_label(inspection.width, inspection.height),
        "duration": human_duration(inspection.duration_ms),
        "status": inspection.status,
        "reason": inspection.reason,
        "display": _classification_display(inspection.status, inspection.reason, phase),
        "tag": _classification_tag(inspection.status, phase),
        "modifiedAt": inspection.modified_at.isoformat() if inspection.modified_at else None,
    }


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value
