"""Manage JianYing Pro process lifecycle and foreground window focus."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time

import psutil

from .env import JianYingEnv
from .models import ProcessStatus


MAIN_PROCESS_NAME = "JianyingPro.exe"
TRAY_PROCESS_NAME = "JianyingProTray.exe"
MAIN_WINDOW_TITLE = "剪映专业版"
SW_RESTORE = 9


class JianYingProcess:
    STARTUP_TIMEOUT = 30

    def __init__(self, env: JianYingEnv | None = None):
        self.env = env or JianYingEnv()

    def status(self) -> ProcessStatus:
        try:
            main_pids = self._process_ids(MAIN_PROCESS_NAME)
            tray_pids = self._process_ids(TRAY_PROCESS_NAME)
        except FileNotFoundError:
            return ProcessStatus.NOT_INSTALLED

        if main_pids:
            return ProcessStatus.RUNNING if self.find_main_window() is not None else ProcessStatus.BACKGROUND
        if tray_pids:
            return ProcessStatus.TRAY_ONLY
        return ProcessStatus.STOPPED

    def launch(self, wait: bool = True, timeout: int | None = None) -> ProcessStatus:
        info = self.env.info
        subprocess.Popen([str(info.launcher_path)], cwd=str(info.install_dir))
        if not wait:
            return ProcessStatus.STARTING

        deadline = time.time() + (timeout or self.STARTUP_TIMEOUT)
        while time.time() <= deadline:
            status = self.status()
            if status == ProcessStatus.RUNNING:
                return status
            time.sleep(1)
        return self.status()

    def exit(self, force: bool = False, timeout: int = 10) -> ProcessStatus:
        """Close JianYing main/editor process while preserving the tray."""
        self._taskkill(MAIN_PROCESS_NAME, force=force)
        deadline = time.time() + timeout
        while time.time() <= deadline:
            status = self.status()
            if status in {ProcessStatus.STOPPED, ProcessStatus.TRAY_ONLY}:
                return status
            time.sleep(0.5)
        return self.status()

    def close_main_window(self, force: bool = False, timeout: int = 10) -> ProcessStatus:
        """Close only JianYingPro.exe, preserving JianYingProTray.exe.

        JianYingPro.exe ignores WM_CLOSE, so we always use /F (force kill)
        regardless of the *force* parameter.  The parameter is kept for API
        compatibility but the behaviour is the same.
        """
        if self.status() in {ProcessStatus.STOPPED, ProcessStatus.TRAY_ONLY}:
            return self.status()

        # Always force-kill: JianYingPro.exe ignores graceful WM_CLOSE
        self._taskkill(MAIN_PROCESS_NAME, force=True)
        deadline = time.time() + timeout
        while time.time() <= deadline:
            status = self.status()
            if status in {ProcessStatus.STOPPED, ProcessStatus.TRAY_ONLY}:
                return status
            time.sleep(0.5)
        return self.status()

    def restart_jianying(self, close_timeout: int = 5, launch_timeout: int | None = None) -> ProcessStatus:
        """Close the main editor process (force-kill), keep tray alive, then relaunch."""
        close_status = self.close_main_window(timeout=close_timeout)
        if close_status not in {ProcessStatus.STOPPED, ProcessStatus.TRAY_ONLY}:
            return close_status
        return self.launch(wait=True, timeout=launch_timeout or self.STARTUP_TIMEOUT)

    def find_main_window(self) -> int | None:
        if os.name != "nt":
            return None
        try:
            user32 = ctypes.windll.user32
        except AttributeError:
            return None

        matches: list[int] = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def enum_callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _window_text(user32, hwnd)
            class_name = _class_name(user32, hwnd)
            if title == MAIN_WINDOW_TITLE and _is_jianying_window_class(class_name):
                matches.append(int(hwnd))
            return True

        user32.EnumWindows(enum_callback, 0)
        return matches[0] if matches else None

    def focus_main_window(self) -> bool:
        hwnd = self.find_main_window()
        if hwnd is None:
            return False
        if os.name != "nt":
            return False
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        our_tid = kernel32.GetCurrentThreadId()
        their_tid = user32.GetWindowThreadProcessId(hwnd, None)
        attached = bool(their_tid and user32.AttachThreadInput(our_tid, their_tid, True))
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            if hasattr(user32, "BringWindowToTop"):
                user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(our_tid, their_tid, False)
        return self._wait_for_foreground(hwnd, timeout=1.5)

    def _wait_for_foreground(self, hwnd: int, timeout: float) -> bool:
        user32 = ctypes.windll.user32
        deadline = time.time() + timeout
        while time.time() <= deadline:
            if int(user32.GetForegroundWindow()) == int(hwnd):
                return True
            time.sleep(0.05)
        return False

    def _process_ids(self, image_name: str) -> list[int]:
        ids: list[int] = []
        for process in psutil.process_iter(["name", "pid"]):
            try:
                if (process.info.get("name") or "").lower() == image_name.lower():
                    ids.append(int(process.info["pid"]))
            except (psutil.Error, TypeError, ValueError):
                continue
        return ids

    @staticmethod
    def _taskkill(image_name: str, *, force: bool) -> None:
        command = ["taskkill", "/IM", image_name]
        if force:
            command.insert(1, "/F")
        subprocess.run(command, capture_output=True, timeout=5)


def _is_jianying_window_class(class_name: str) -> bool:
    return class_name.startswith("Qt") and class_name.endswith("QWindowIcon")


def _window_text(user32, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(length + 1, 256))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _class_name(user32, hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value
