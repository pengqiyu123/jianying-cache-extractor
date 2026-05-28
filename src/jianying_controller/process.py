"""Manage JianYing Pro process: launch, exit, status."""

import os
import signal
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
    TRAY_ONLY = "tray_only"


class JianYingProcess:
    """Control JianYing Pro process lifecycle."""

    STARTUP_TIMEOUT = 30  # seconds to wait for startup

    def __init__(self, env: Optional[JianYingEnv] = None):
        self.env = env or JianYingEnv()

    def status(self) -> ProcessStatus:
        """Check current JianYing process status."""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq JianyingPro.exe"],
                capture_output=True, text=True, timeout=5,
            )
            main_running = "JianyingPro.exe" in result.stdout

            tray_result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq JianyingProTray.exe"],
                capture_output=True, text=True, timeout=5,
            )
            tray_running = "JianyingProTray.exe" in tray_result.stdout

            if main_running:
                return ProcessStatus.RUNNING
            elif tray_running:
                return ProcessStatus.TRAY_ONLY
            else:
                return ProcessStatus.STOPPED
        except FileNotFoundError:
            return ProcessStatus.NOT_INSTALLED

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
