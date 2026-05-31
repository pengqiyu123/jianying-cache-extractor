from __future__ import annotations

from pathlib import Path

from jianying_controller.models import JianYingInfo, ProcessStatus
from jianying_controller.process import JianYingProcess


class FakeEnv:
    def __init__(self, launcher_path: Path):
        self.info = JianYingInfo(
            install_dir=launcher_path.parent.parent,
            exe_path=launcher_path.parent / "10.7.0.14095" / "JianyingPro.exe",
            launcher_path=launcher_path,
            draft_dir=launcher_path.parent.parent / "User Data" / "Projects" / "com.lveditor.draft",
            version="10.7.0.14095",
        )


def test_restart_closes_only_main_process_and_preserves_tray(monkeypatch, tmp_path) -> None:
    launcher = tmp_path / "JianyingPro" / "Apps" / "JianyingPro.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("launcher")
    calls: list[list[str]] = []
    statuses = iter(
        [
            ProcessStatus.RUNNING,
            ProcessStatus.TRAY_ONLY,
            ProcessStatus.RUNNING,
        ]
    )

    process = JianYingProcess(env=FakeEnv(launcher))
    monkeypatch.setattr(process, "status", lambda: next(statuses, ProcessStatus.RUNNING))

    def fake_run(command, **kwargs):
        calls.append(list(command))

        class Result:
            stdout = ""

        return Result()

    def fake_popen(command, **kwargs):
        calls.append(list(command))

        class PopenResult:
            pass

        return PopenResult()

    monkeypatch.setattr("jianying_controller.process.subprocess.run", fake_run)
    monkeypatch.setattr("jianying_controller.process.subprocess.Popen", fake_popen)
    monkeypatch.setattr("jianying_controller.process.time.sleep", lambda _seconds: None)

    assert process.restart_jianying() == ProcessStatus.RUNNING

    flattened = " ".join(" ".join(call) for call in calls)
    assert "JianyingPro.exe" in flattened
    assert "JianyingProTray.exe" not in flattened
    assert [str(launcher)] in calls


def test_focus_main_window_returns_false_when_no_window(monkeypatch, tmp_path) -> None:
    launcher = tmp_path / "JianyingPro" / "Apps" / "JianyingPro.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("launcher")
    process = JianYingProcess(env=FakeEnv(launcher))
    monkeypatch.setattr(process, "find_main_window", lambda: None)

    assert process.focus_main_window() is False


def test_compound_default_hotkey_is_shift_g_and_sequence_sent() -> None:
    from jianying_controller.compound_clip import DEFAULT_PRECOMPOSE_HOTKEY, run_compound_clip_sequence

    sent: list[tuple[str, ...]] = []
    result = run_compound_clip_sequence(focus=lambda: True, sender=lambda keys: sent.append(tuple(keys)), sleeper=lambda _s: None)

    assert DEFAULT_PRECOMPOSE_HOTKEY == "shift+g"
    assert result.status == "sent"
    assert sent == [("ctrl", "a"), ("alt", "g"), ("ctrl", "a"), ("shift", "g")]


def test_compound_focus_failure_does_not_send_hotkeys() -> None:
    from jianying_controller.compound_clip import run_compound_clip_sequence

    sent: list[tuple[str, ...]] = []
    result = run_compound_clip_sequence(focus=lambda: False, sender=lambda keys: sent.append(tuple(keys)), sleeper=lambda _s: None)

    assert result.status == "focus_failed"
    assert sent == []


def test_parse_hotkey_rejects_dangerous_or_invalid_values() -> None:
    from jianying_controller.compound_clip import parse_hotkey

    assert parse_hotkey("shift+g") == ("shift", "g")
    assert parse_hotkey("ctrl+g") == ("ctrl", "g")
    assert parse_hotkey("") is None
    assert parse_hotkey("shift") is None
    assert parse_hotkey("win+r") is None
    assert parse_hotkey("ctrl+alt+delete") is None


def test_auto_import_focus_failure_does_not_send_ctrl_i(tmp_path) -> None:
    from jianying_controller.auto_import import AutoImportWin32, auto_import_file

    mp4 = tmp_path / "cache.mp4"
    mp4.write_bytes(b"data")
    api = AutoImportWin32(
        find_main_window=lambda: 100,
        focus_window=lambda _hwnd: False,
        wait_foreground=lambda _hwnd, _timeout: False,
        send_ctrl_i=lambda: (_ for _ in ()).throw(AssertionError("should not send ctrl+i")),
        find_import_dialog=lambda _timeout: None,
        close_existing_dialogs=lambda _timeout, _attempts: None,
        set_file_path=lambda _dialog, _path: True,
        click_open=lambda _dialog: True,
    )

    result = auto_import_file(mp4, win32=api)

    assert result.status == "focus_failed"


def test_auto_import_old_dialog_close_failure_returns_error(tmp_path) -> None:
    from jianying_controller.auto_import import AutoImportWin32, auto_import_file

    mp4 = tmp_path / "cache.mp4"
    mp4.write_bytes(b"data")
    api = AutoImportWin32(
        find_main_window=lambda: 100,
        focus_window=lambda _hwnd: True,
        wait_foreground=lambda _hwnd, _timeout: True,
        send_ctrl_i=lambda: None,
        find_import_dialog=lambda _timeout: None,
        close_existing_dialogs=lambda _timeout, _attempts: 200,
        set_file_path=lambda _dialog, _path: True,
        click_open=lambda _dialog: True,
    )

    result = auto_import_file(mp4, win32=api)

    assert result.status == "old_dialog_close_failed"
    assert result.error_detail == "旧导入窗口无法关闭，请手动关闭后重试。"


def test_auto_import_uses_dialog_set_text_and_click_not_clipboard(tmp_path, monkeypatch) -> None:
    from jianying_controller.auto_import import AutoImportWin32, auto_import_file

    mp4 = tmp_path / "cache.mp4"
    mp4.write_bytes(b"data")
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr("builtins.__import__", __import__)
    api = AutoImportWin32(
        find_main_window=lambda: 100,
        focus_window=lambda hwnd: calls.append(("focus", hwnd)) or True,
        wait_foreground=lambda hwnd, timeout: calls.append(("foreground", hwnd)) or True,
        send_ctrl_i=lambda: calls.append(("ctrl_i", True)),
        find_import_dialog=lambda timeout: 300,
        close_existing_dialogs=lambda timeout, attempts: None,
        set_file_path=lambda dialog, path: calls.append(("set_path", path)) or True,
        click_open=lambda dialog: calls.append(("click_open", dialog)) or True,
    )

    result = auto_import_file(mp4, win32=api)

    assert result.status == "sent"
    assert ("ctrl_i", True) in calls
    assert ("set_path", str(mp4)) in calls
    assert ("click_open", 300) in calls
