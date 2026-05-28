"""Detect JianYing Pro installation, version, and draft folder location."""

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class JianYingInfo:
    install_dir: Path
    exe_path: Path
    launcher_path: Path
    version: str
    full_version: str
    draft_dir: Path
    user_data_dir: Path
    tray_exe: Path = field(default=None)
    ffmpeg_path: Path = field(default=None)


class JianYingEnv:
    """Discover JianYing Pro installation and environment."""

    APPDATA_LOCAL = os.environ.get("LOCALAPPDATA", "")

    def __init__(self, custom_path: Optional[str] = None):
        self._info: Optional[JianYingInfo] = None
        self._custom_path = custom_path

    def detect(self) -> JianYingInfo:
        """Auto-detect JianYing installation. Returns JianYingInfo."""
        if self._info:
            return self._info

        install_dir = self._find_install_dir()
        if not install_dir:
            raise FileNotFoundError(
                "JianYing Pro not found. "
                "Searched LOCALAPPDATA and custom paths."
            )

        self._info = self._build_info(install_dir)
        return self._info

    @property
    def info(self) -> JianYingInfo:
        if not self._info:
            return self.detect()
        return self._info

    def _find_install_dir(self) -> Optional[Path]:
        candidates = []

        if self._custom_path:
            candidates.append(Path(self._custom_path))

        if self.APPDATA_LOCAL:
            candidates.append(Path(self.APPDATA_LOCAL) / "JianyingPro")

        for d in candidates:
            if d.is_dir() and (d / "Apps" / "JianyingPro.exe").exists():
                return d

        # Registry fallback
        reg_path = self._search_registry()
        if reg_path:
            p = Path(reg_path)
            if p.is_dir():
                return p

        return None

    def _search_registry(self) -> Optional[str]:
        try:
            for hive in ["HKCU", "HKLM"]:
                result = subprocess.run(
                    [
                        "reg", "query",
                        f"{hive}\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
                        "/s", "/f", "JianyingPro",
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if "InstallLocation" in line or "DisplayIcon" in line:
                        parts = line.split("REG_SZ")
                        if len(parts) >= 2:
                            val = parts[1].strip().strip('"')
                            if "JianyingPro" in val:
                                return str(Path(val).parent)
        except Exception:
            pass
        return None

    def _build_info(self, install_dir: Path) -> JianYingInfo:
        apps_dir = install_dir / "Apps"
        user_data = install_dir / "User Data"
        draft_dir = user_data / "Projects" / "com.lveditor.draft"

        # Find versioned directory
        version, full_version, version_dir = self._detect_version(apps_dir)

        exe_path = version_dir / "JianyingPro.exe"
        tray_exe = version_dir / "JianyingProTray.exe"
        ffmpeg_path = version_dir / "ffmpeg.exe" if (version_dir / "ffmpeg.exe").exists() else None

        return JianYingInfo(
            install_dir=install_dir,
            exe_path=exe_path,
            launcher_path=apps_dir / "JianyingPro.exe",
            version=version,
            full_version=full_version,
            draft_dir=draft_dir,
            user_data_dir=user_data,
            tray_exe=tray_exe,
            ffmpeg_path=ffmpeg_path,
        )

    def _detect_version(self, apps_dir: Path):
        # Try reading version from packet XML first
        packet_file = apps_dir / "JianyingProPacket.xml"
        if packet_file.exists():
            try:
                tree = ET.parse(packet_file)
                root = tree.getroot()
                full_ver = root.findtext("full_appver", "")
                ver = root.findtext("appver", "")
                if full_ver:
                    version_dir = apps_dir / full_ver
                    if version_dir.is_dir():
                        return ver, full_ver, version_dir
            except Exception:
                pass

        # Fallback: scan for versioned directories
        version_dirs = sorted(
            [d for d in apps_dir.iterdir() if d.is_dir() and d.name[0].isdigit()],
            key=lambda d: d.name,
            reverse=True,
        )
        if version_dirs:
            vd = version_dirs[0]
            return vd.name.split(".")[0], vd.name, vd

        raise FileNotFoundError("No JianYing version directory found under Apps/")

    def list_drafts(self) -> list[dict]:
        """List all existing drafts with metadata."""
        drafts = []
        draft_dir = self.info.draft_dir
        if not draft_dir.is_dir():
            return drafts

        for d in sorted(draft_dir.iterdir()):
            if not d.is_dir():
                continue
            meta_file = d / "draft_meta_info.json"
            cover_file = d / "draft_cover.jpg"
            draft_content = d / "draft_content.json"

            entry = {
                "name": d.name,
                "path": str(d),
                "has_content": draft_content.exists(),
                "has_cover": cover_file.exists(),
                "content_size": draft_content.stat().st_size if draft_content.exists() else 0,
            }

            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        raw = f.read()
                    # Try to parse - may be encrypted
                    if raw.startswith("{"):
                        meta = json.loads(raw)
                        entry["timedelta"] = meta.get("timedelta", "")
                        entry["duration"] = meta.get("duration", 0)
                        entry["platform"] = meta.get("platform", "")
                except Exception:
                    entry["meta_encrypted"] = True

            entry["content_encrypted"] = self._is_encrypted(draft_content) if draft_content.exists() else None
            drafts.append(entry)

        return drafts

    @staticmethod
    def _is_encrypted(file_path: Path) -> bool:
        """Check if a file is encrypted (not valid JSON/UTF-8)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_char = f.read(1)
            return first_char != "{" and first_char != "["
        except UnicodeDecodeError:
            return True

    def summary(self) -> str:
        """Return a human-readable summary of the detected environment."""
        i = self.info
        lines = [
            f"JianYing Pro v{i.version} ({i.full_version})",
            f"  Install:   {i.install_dir}",
            f"  EXE:       {i.exe_path}",
            f"  Launcher:  {i.launcher_path}",
            f"  Drafts:    {i.draft_dir}",
            f"  UserData:  {i.user_data_dir}",
        ]
        if i.ffmpeg_path:
            lines.append(f"  FFmpeg:    {i.ffmpeg_path}")
        if i.tray_exe:
            lines.append(f"  Tray:      {i.tray_exe}")

        drafts = self.list_drafts()
        lines.append(f"  Drafts:    {len(drafts)} projects found")
        encrypted_count = sum(1 for d in drafts if d.get("content_encrypted"))
        if encrypted_count:
            lines.append(f"             ({encrypted_count} encrypted)")

        return "\n".join(lines)
