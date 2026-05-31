"""Detect JianYing Pro installation, version, and draft folder location."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import DraftFolder, JianYingInfo


class JianYingEnv:
    """Discover the local JianYing Pro installation."""

    def __init__(self, custom_path: str | Path | None = None):
        self._custom_path = Path(custom_path) if custom_path is not None else None
        self._info: JianYingInfo | None = None

    @property
    def info(self) -> JianYingInfo:
        return self.detect()

    def detect(self) -> JianYingInfo:
        if self._info is not None:
            return self._info

        install_dir = self._find_install_dir()
        if install_dir is None:
            raise FileNotFoundError("JianYing Pro not found.")

        apps_dir = install_dir / "Apps"
        launcher_path = apps_dir / "JianyingPro.exe"
        version_dir = self._find_latest_version_dir(apps_dir)
        exe_path = version_dir / "JianyingPro.exe"
        draft_dir = install_dir / "User Data" / "Projects" / "com.lveditor.draft"

        self._info = JianYingInfo(
            install_dir=install_dir,
            exe_path=exe_path,
            launcher_path=launcher_path,
            draft_dir=draft_dir,
            version=version_dir.name,
        )
        return self._info

    def list_drafts(self) -> list[DraftFolder]:
        draft_root = self.info.draft_dir
        if not draft_root.is_dir():
            return []
        drafts: list[DraftFolder] = []
        for path in draft_root.iterdir():
            if not path.is_dir():
                continue
            stat = path.stat()
            drafts.append(
                DraftFolder(
                    path=path,
                    name=path.name,
                    modified_at=_datetime_from_timestamp(max(stat.st_mtime, stat.st_ctime)),
                    has_combination_cache=(path / "Resources" / "combination").is_dir(),
                )
            )
        return sorted(drafts, key=lambda draft: draft.modified_at, reverse=True)

    def _find_install_dir(self) -> Path | None:
        if self._custom_path is not None:
            return self._custom_path if (self._custom_path / "Apps" / "JianyingPro.exe").exists() else None

        candidates: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "JianyingPro")

        for candidate in candidates:
            if (candidate / "Apps" / "JianyingPro.exe").exists():
                return candidate

        registry_path = self._search_registry()
        if registry_path is not None and (registry_path / "Apps" / "JianyingPro.exe").exists():
            return registry_path
        return None

    def _search_registry(self) -> Path | None:
        try:
            result = subprocess.run(
                [
                    "reg",
                    "query",
                    r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    "/s",
                    "/f",
                    "JianyingPro",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        for line in result.stdout.splitlines():
            if "InstallLocation" not in line:
                continue
            parts = line.split("REG_SZ", 1)
            if len(parts) == 2:
                return Path(parts[1].strip().strip('"'))
        return None

    @staticmethod
    def _find_latest_version_dir(apps_dir: Path) -> Path:
        version_dirs = [
            path
            for path in apps_dir.iterdir()
            if path.is_dir() and (path / "JianyingPro.exe").exists() and path.name[:1].isdigit()
        ]
        if not version_dirs:
            raise FileNotFoundError("No JianYing version directory found under Apps.")
        return sorted(version_dirs, key=lambda path: _version_key(path.name), reverse=True)[0]


def _version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _datetime_from_timestamp(timestamp: float):
    from datetime import datetime

    return datetime.fromtimestamp(timestamp)
