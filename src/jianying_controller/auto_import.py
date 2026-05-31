"""One-click import through JianYing's Windows import dialog."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import ImportResult
from .process import MAIN_WINDOW_TITLE, _is_jianying_window_class


DIALOG_CLASS = "#32770"
DIALOG_TITLE_FRAGMENT = "选择媒体资源"
EDIT_CONTROL_ID = 1148
OPEN_BUTTON_CONTROL_ID = 1
BM_CLICK = 0x00F5
WM_CLOSE = 0x0010
SW_RESTORE = 9
VK_CONTROL = 0x11
VK_I = 0x49
KEYEVENTF_KEYUP = 0x0002


@dataclass(frozen=True)
class AutoImportWin32:
    find_main_window: Callable[[], int | None]
    focus_window: Callable[[int], bool]
    wait_foreground: Callable[[int, float], bool]
    send_ctrl_i: Callable[[], None]
    find_import_dialog: Callable[[float], int | None]
    close_existing_dialogs: Callable[[float, int], int | None]
    set_file_path: Callable[[int, str], bool]
    click_open: Callable[[int], bool]


def auto_import_file(
    mp4_path: str | Path,
    *,
    win32: AutoImportWin32 | None = None,
    dialog_timeout_seconds: float = 5.0,
    close_timeout_seconds: float = 2.0,
    close_max_attempts: int = 5,
) -> ImportResult:
    path = Path(mp4_path)
    if not path.is_file():
        return ImportResult(status="file_not_found", error_detail=f"文件不存在: {path}")
    win32 = win32 or _default_win32()

    stale_dialog = win32.close_existing_dialogs(close_timeout_seconds, close_max_attempts)
    if stale_dialog is not None:
        return ImportResult(status="old_dialog_close_failed", error_detail="旧导入窗口无法关闭，请手动关闭后重试。")

    main_hwnd = win32.find_main_window()
    if main_hwnd is None:
        return ImportResult(status="window_not_found", error_detail="未找到剪映主窗口。")
    if not win32.focus_window(main_hwnd) or not win32.wait_foreground(main_hwnd, 1.5):
        return ImportResult(status="focus_failed", error_detail="无法聚焦剪映主窗口，已取消发送快捷键。")

    win32.send_ctrl_i()
    dialog_hwnd = win32.find_import_dialog(dialog_timeout_seconds)
    if dialog_hwnd is None:
        return ImportResult(status="dialog_timeout", error_detail="导入对话框未出现，请确认已进入剪映编辑界面。")
    if not win32.set_file_path(dialog_hwnd, str(path)):
        return ImportResult(status="control_error", error_detail="路径没有成功写入文件名输入框。")
    if not win32.click_open(dialog_hwnd):
        return ImportResult(status="control_error", error_detail="打开按钮点击失败。")
    return ImportResult(status="sent")


def _default_win32() -> AutoImportWin32:
    return AutoImportWin32(
        find_main_window=_find_main_window,
        focus_window=_focus_window,
        wait_foreground=_wait_foreground,
        send_ctrl_i=_send_ctrl_i,
        find_import_dialog=_find_import_dialog,
        close_existing_dialogs=_close_existing_dialogs,
        set_file_path=_set_file_path,
        click_open=_click_open,
    )


def _user32():
    return ctypes.windll.user32


def _find_main_window() -> int | None:
    user32 = _user32()
    matches: list[int] = []

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            title = _window_text(hwnd)
            class_name = _class_name(hwnd)
            if title == MAIN_WINDOW_TITLE and _is_jianying_window_class(class_name):
                matches.append(int(hwnd))
        return True

    user32.EnumWindows(_enum_proc(callback), 0)
    return matches[0] if matches else None


def _focus_window(hwnd: int) -> bool:
    user32 = _user32()
    kernel32 = ctypes.windll.kernel32
    our_tid = kernel32.GetCurrentThreadId()
    their_tid = user32.GetWindowThreadProcessId(hwnd, None)
    attached = bool(their_tid and user32.AttachThreadInput(our_tid, their_tid, True))
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        if hasattr(user32, "BringWindowToTop"):
            user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(our_tid, their_tid, False)


def _wait_foreground(hwnd: int, timeout: float) -> bool:
    user32 = _user32()
    deadline = time.time() + timeout
    while time.time() <= deadline:
        if int(user32.GetForegroundWindow()) == int(hwnd):
            return True
        time.sleep(0.05)
    return False


def _send_ctrl_i() -> None:
    user32 = _user32()
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_I, 0, 0, 0)
    user32.keybd_event(VK_I, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _find_import_dialog(timeout: float) -> int | None:
    user32 = _user32()
    deadline = time.time() + timeout
    while time.time() <= deadline:
        matches: list[int] = []

        def callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd) and _class_name(hwnd) == DIALOG_CLASS:
                if DIALOG_TITLE_FRAGMENT in _window_text(hwnd):
                    matches.append(int(hwnd))
            return True

        user32.EnumWindows(_enum_proc(callback), 0)
        if matches:
            return matches[0]
        time.sleep(0.2)
    return None


def _close_existing_dialogs(timeout: float, max_attempts: int) -> int | None:
    user32 = _user32()
    deadline = time.time() + timeout
    attempts = 0
    while attempts < max_attempts and time.time() <= deadline:
        hwnd = _find_import_dialog(0.05)
        if hwnd is None:
            return None
        attempts += 1
        user32.SendMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.2)
        if not user32.IsWindow(hwnd):
            continue
    return _find_import_dialog(0.05)


def _set_file_path(dialog_hwnd: int, file_path: str) -> bool:
    """Type the file path into the filename edit control character by character.

    Windows file dialogs (and JianYing's custom variant) ignore text set via
    ``SetDlgItemTextW`` / ``SetWindowTextW`` — the edit control visually
    updates but the dialog's internal selection state does NOT sync.  The
    result is the "Open" button does nothing because the dialog thinks no
    file is selected.

    Sending ``WM_CHAR`` for each character triggers the dialog's internal
    autocomplete and selection logic correctly.  Tested 2026-05-31.
    """
    # Find the Edit child inside the ComboBoxEx32 (id=1148)
    combo_ex = _user32().GetDlgItem(dialog_hwnd, EDIT_CONTROL_ID)
    if not combo_ex:
        return False

    edit_hwnd = None

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _find_edit(hwnd, _lp):
        nonlocal edit_hwnd
        buf = ctypes.create_unicode_buffer(256)
        _user32().GetClassNameW(hwnd, buf, 256)
        if buf.value == "Edit":
            edit_hwnd = int(hwnd)
        return True

    _user32().EnumChildWindows(combo_ex, _find_edit, 0)
    if not edit_hwnd:
        return False

    # Select all existing text so we overwrite it
    EM_SETSEL = 0x00B1
    _user32().SendMessageW(edit_hwnd, EM_SETSEL, 0, -1)
    time.sleep(0.05)

    # Type each character
    WM_CHAR = 0x0102
    for ch in file_path:
        _user32().SendMessageW(edit_hwnd, WM_CHAR, ord(ch), 0)

    return True


def _click_open(dialog_hwnd: int) -> bool:
    """Send Enter key to the dialog to confirm the file selection.

    ``BM_CLICK`` and ``WM_COMMAND`` do NOT work on JianYing's custom
    file dialog — the button visually exists but the click is silently
    ignored.  Sending Enter via ``keybd_event`` after the Edit control
    has focus is the only method that works.  Tested 2026-05-31.
    """
    # Focus the dialog
    _user32().SetForegroundWindow(dialog_hwnd)
    time.sleep(0.2)

    # Send Enter
    VK_RETURN = 0x0D
    KEYEVENTF_KEYUP = 0x0002
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
    return True


def _window_text(hwnd: int) -> str:
    user32 = _user32()
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(length + 1, 256))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _class_name(hwnd: int) -> str:
    user32 = _user32()
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _enum_proc(callback):
    return ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(callback)
