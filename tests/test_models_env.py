from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

import pytest

from jianying_controller.models import (
    CandidateStatus,
    CacheOrigin,
    DraftFolder,
    JianYingInfo,
    ProcessStatus,
    SourceMode,
)


def test_env_detects_launcher_version_and_draft_dir(tmp_path, monkeypatch) -> None:
    from jianying_controller.env import JianYingEnv

    install = tmp_path / "JianyingPro"
    apps = install / "Apps"
    version_dir = apps / "10.7.0.14095"
    draft_dir = install / "User Data" / "Projects" / "com.lveditor.draft"
    version_dir.mkdir(parents=True)
    draft_dir.mkdir(parents=True)
    (apps / "JianyingPro.exe").write_text("launcher")
    (version_dir / "JianyingPro.exe").write_text("main")

    env = JianYingEnv(custom_path=install)
    info = env.detect()

    assert info.install_dir == install
    assert info.launcher_path == apps / "JianyingPro.exe"
    assert info.exe_path == version_dir / "JianyingPro.exe"
    assert info.version == "10.7.0.14095"
    assert info.draft_dir == draft_dir


def test_env_returns_not_installed_for_missing_install(tmp_path) -> None:
    from jianying_controller.env import JianYingEnv

    env = JianYingEnv(custom_path=tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        env.detect()


def test_core_enum_values_match_plan() -> None:
    assert SourceMode.AUTO.value == "auto"
    assert CandidateStatus.AVAILABLE.value == "available"
    assert CacheOrigin.CLOUD_CACHE.value == "cloud_cache"
    assert ProcessStatus.TRAY_ONLY.value == "tray_only"


def test_models_are_immutable() -> None:
    info = JianYingInfo(
        install_dir=Path("C:/JianyingPro"),
        exe_path=Path("C:/JianyingPro/Apps/10.7.0.14095/JianYingPro.exe"),
        launcher_path=Path("C:/JianyingPro/Apps/JianYingPro.exe"),
        draft_dir=Path("C:/JianyingPro/User Data/Projects/com.lveditor.draft"),
        version="10.7.0.14095",
    )

    with pytest.raises(FrozenInstanceError):
        info.version = "changed"  # type: ignore[misc]


def test_draft_folder_combination_flag_defaults_false() -> None:
    draft = DraftFolder(path=Path("draft"), name="draft", modified_at=datetime(2026, 5, 31))

    assert draft.has_combination_cache is False
