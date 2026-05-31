"""Keyboard automation for JianYing compound clip operations."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Callable, Sequence

from .models import CompoundResult
from .process import JianYingProcess


DEFAULT_PRECOMPOSE_HOTKEY = "shift+g"
MODIFIERS = {"ctrl", "shift", "alt"}
DENIED_KEYS = {"delete", "esc", "escape", "tab", "enter", "return"}
VK_CODES = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
}
KEYEVENTF_KEYUP = 0x0002


def parse_hotkey(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    parts = [part.strip().lower() for part in value.split("+") if part.strip()]
    if len(parts) != 2:
        return None
    modifier, key = parts
    if modifier not in MODIFIERS:
        return None
    if key in MODIFIERS or key.startswith("win") or key in DENIED_KEYS:
        return None
    if len(key) != 1 or not key.isalnum():
        return None
    return modifier, key


def run_compound_clip_sequence(
    hotkey: str = DEFAULT_PRECOMPOSE_HOTKEY,
    *,
    focus: Callable[[], bool] | None = None,
    sender: Callable[[Sequence[str]], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> CompoundResult:
    parsed = parse_hotkey(hotkey)
    if parsed is None:
        return CompoundResult(status="hotkey_missing", warnings=[f"invalid hotkey: {hotkey!r}"])

    focus = focus or JianYingProcess().focus_main_window
    sender = sender or send_hotkey
    if not focus():
        return CompoundResult(status="focus_failed")

    sequence: list[tuple[str, ...]] = [("ctrl", "a"), ("alt", "g"), ("ctrl", "a"), parsed]
    delays = [0.5, 2.4, 0.8, 0.0]
    for keys, delay in zip(sequence, delays, strict=True):
        sender(keys)
        if delay > 0:
            sleeper(delay)
    return CompoundResult(status="sent")


def run_uncompose_clip_sequence(
    *,
    focus: Callable[[], bool] | None = None,
    sender: Callable[[Sequence[str]], None] | None = None,
) -> CompoundResult:
    focus = focus or JianYingProcess().focus_main_window
    sender = sender or send_hotkey
    if not focus():
        return CompoundResult(status="focus_failed")
    sender(("alt", "shift", "g"))
    return CompoundResult(status="sent")


def send_hotkey(keys: Sequence[str]) -> None:
    try:
        _send_hotkey_win32(keys)
    except Exception:
        import pyautogui

        pyautogui.hotkey(*keys)


def _send_hotkey_win32(keys: Sequence[str]) -> None:
    user32 = ctypes.windll.user32
    resolved = [_vk_code(key) for key in keys]
    for code in resolved:
        user32.keybd_event(code, 0, 0, 0)
    for code in reversed(resolved):
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)


def _vk_code(key: str) -> int:
    lowered = key.lower()
    if lowered in VK_CODES:
        return VK_CODES[lowered]
    if len(lowered) == 1 and lowered.isalnum():
        return ord(lowered.upper())
    raise ValueError(f"unsupported key: {key}")
