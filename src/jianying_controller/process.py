"""Manage JianYing Pro process: launch, exit, status."""

import csv
import ctypes
import os
import subprocess
import time
from enum import Enum
from typing import Optional

from .env import JianYingEnv


class ProcessStatus(str, Enum):
    NOT_INSTALLED = "not_installed"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    BACKGROUND = "background"
    TRAY_ONLY = "tray_only"


class JianYingProcess:
    """Control JianYing Pro process lifecycle."""

    STARTUP_TIMEOUT = 30  # seconds to wait for startup

    def __init__(self, env: Optional[JianYingEnv] = None):
        self.env = env or JianYingEnv()

    def status(self) -> ProcessStatus:
        """Check current JianYing process status."""
        try:
            main_process_ids = self._process_ids("JianyingPro.exe")
            tray_process_ids = self._process_ids("JianyingProTray.exe")

            if main_process_ids:
                if self._has_visible_window(main_process_ids):
                    return ProcessStatus.RUNNING
                return ProcessStatus.BACKGROUND
            elif tray_process_ids:
                return ProcessStatus.TRAY_ONLY
            else:
                return ProcessStatus.STOPPED
        except FileNotFoundError:
            return ProcessStatus.NOT_INSTALLED

    def _process_ids(self, image_name: str) -> list[int]:
        """Return process IDs for an executable image name."""
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        process_ids: list[int] = []
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) < 2 or row[0].lower() != image_name.lower():
                continue
            try:
                process_ids.append(int(row[1]))
            except ValueError:
                continue
        return process_ids

    def _has_visible_window(self, process_ids: list[int]) -> bool:
        """Return True when any process owns a visible, titled window."""
        if not process_ids:
            return False
        if os.name != "nt":
            return True

        try:
            user32 = ctypes.windll.user32
            from ctypes import wintypes
        except Exception:
            return True

        target_ids = set(process_ids)
        found = False

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd, _lparam):
            nonlocal found
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in target_ids and user32.IsWindowVisible(hwnd):
                if user32.GetWindowTextLengthW(hwnd) > 0:
                    found = True
                    return False
            return True

        try:
            user32.EnumWindows(enum_callback, 0)
        except Exception:
            return True
        return found

    def launch(self, wait: bool = True, timeout: Optional[int] = None) -> ProcessStatus:
        """Launch JianYing Pro.

        Args:
            wait: Block until the process is confirmed running.
            timeout: Max seconds to wait (default: STARTUP_TIMEOUT).

        Returns:
            Final process status.
        """
        current = self.status()
        if current == ProcessStatus.RUNNING:
            return current

        info = self.env.info
        exe = str(info.launcher_path)

        # Launch via the launcher (handles version resolution)
        subprocess.Popen(
            [exe],
            cwd=str(info.install_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        if not wait:
            return ProcessStatus.STARTING

        deadline = time.time() + (timeout or self.STARTUP_TIMEOUT)
        while time.time() < deadline:
            time.sleep(1)
            s = self.status()
            if s == ProcessStatus.RUNNING:
                return s

        return self.status()

    def exit(self, force: bool = False, timeout: int = 10) -> ProcessStatus:
        """Exit JianYing Pro completely, including tray process.

        Args:
            force: Use taskkill /F to force-kill all JianYing processes.
            timeout: Seconds to wait for graceful exit.

        Returns:
            Final process status.
        """
        if self.status() == ProcessStatus.STOPPED:
            return ProcessStatus.STOPPED

        if force:
            # Force kill everything at once
            subprocess.run(
                ["taskkill", "/F", "/IM", "JianyingPro.exe"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "JianyingProTray.exe"],
                capture_output=True, timeout=5,
            )
            time.sleep(1)
            return self.status()

        # Graceful attempt: JianYing ignores WM_CLOSE when main window is open,
        # so we try once and fall back to force kill.
        subprocess.run(
            ["taskkill", "/IM", "JianyingPro.exe"],
            capture_output=True, timeout=5,
        )
        time.sleep(2)

        if self.status() == ProcessStatus.TRAY_ONLY:
            subprocess.run(
                ["taskkill", "/IM", "JianyingProTray.exe"],
                capture_output=True, timeout=5,
            )
            time.sleep(1)
            return self.status()

        # Graceful failed, force kill all
        if self.status() != ProcessStatus.STOPPED:
            subprocess.run(
                ["taskkill", "/F", "/IM", "JianyingPro.exe"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "JianyingProTray.exe"],
                capture_output=True, timeout=5,
            )
            time.sleep(1)

        return self.status()

    def _kill_tray(self, force: bool = False):
        """Kill the tray process."""
        flag = "/F" if force else ""
        cmd = ["taskkill", "/IM", "JianyingProTray.exe"]
        if flag:
            cmd.insert(1, flag)
        subprocess.run(cmd, capture_output=True, timeout=5)
        time.sleep(1)

    def open_draft(self, draft_name: str) -> bool:
        """Open a specific draft in JianYing by launching with the draft path.

        This uses JianYing's protocol handler or direct launch.
        JianYing will need to be running or will start automatically.
        """
        info = self.env.info
        draft_path = info.draft_dir / draft_name

        if not draft_path.is_dir():
            return False

        # JianYing supports opening drafts via command line or protocol
        # Try protocol handler first: jianying://
        try:
            os.startfile(str(draft_path))
            return True
        except Exception:
            return False

    def is_idle(self) -> bool:
        """Check if JianYing is running but not actively rendering/exporting.

        Best-effort check based on CPU usage of the process.
        """
        s = self.status()
        if s != ProcessStatus.RUNNING:
            return False

        try:
            result = subprocess.run(
                [
                    "wmic", "process", "where",
                    "name='JianyingPro.exe'",
                    "get", "PercentProcessorTime",
                ],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and line != "PercentProcessorTime":
                    try:
                        cpu = int(line)
                        return cpu < 10
                    except ValueError:
                        continue
        except Exception:
            pass

        return True
