"""pywebview GUI entrypoint."""

from __future__ import annotations

from pathlib import Path

from .api import PythonApi
from .state import (
    APP_TITLE,
    APP_VERSION,
    BADGE_COLORS,
    PHASE_LABELS,
    PROCESS_LABELS,
    REJECTION_LABELS,
    STATUS_MESSAGES,
    USAGE_INSTRUCTIONS,
    GuiState,
    build_request,
    button_states,
    candidate_row,
    empty_state_message,
    format_status_message,
    human_duration,
    human_size,
    resolution_label,
    status_label,
)

__all__ = [
    "APP_TITLE",
    "APP_VERSION",
    "BADGE_COLORS",
    "PHASE_LABELS",
    "PROCESS_LABELS",
    "REJECTION_LABELS",
    "STATUS_MESSAGES",
    "USAGE_INSTRUCTIONS",
    "GuiState",
    "build_request",
    "button_states",
    "candidate_row",
    "empty_state_message",
    "format_status_message",
    "human_duration",
    "human_size",
    "main",
    "resolution_label",
    "status_label",
]


def _start_ui(api: PythonApi) -> None:
    """Called by webview.start() on the UI thread after the window is ready."""
    api.start_process_polling()


def main() -> None:
    import webview

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    api = PythonApi()
    window = webview.create_window(
        title=f"{APP_TITLE} {APP_VERSION}",
        url=str(frontend_dir / "index.html"),
        js_api=api,
        min_size=(1000, 780),
        width=1100,
        height=900,
        text_select=True,
        background_color="#313338",
    )
    api.set_window(window)
    webview.start(func=_start_ui, args=api, debug=False)
