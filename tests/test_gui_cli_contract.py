from __future__ import annotations

from jianying_controller.__main__ import build_parser
from jianying_controller.gui.state import GuiState, button_states, format_status_message
from jianying_controller.models import ProcessStatus, WorkflowPhase


def test_cli_parser_supports_plan_commands() -> None:
    parser = build_parser()

    cases = [
        ["scan", "--auto"],
        ["scan", "--project", "p"],
        ["scan", "--mp4", "m.mp4"],
        ["create", "--auto"],
        ["auto-import", "m.mp4"],
        ["compound-clip", "--hotkey", "shift+g"],
        ["prepare-import", "m.mp4"],
        ["uncompose-clip"],
    ]

    assert [parser.parse_args(case).command for case in cases] == [
        "scan",
        "scan",
        "scan",
        "create",
        "auto-import",
        "compound-clip",
        "prepare-import",
        "uncompose-clip",
    ]


def test_button_states_match_workflow_rules() -> None:
    state = button_states(
        process=ProcessStatus.RUNNING,
        phase=WorkflowPhase.RESTARTED,
        selected_project=True,
        confirmed_open=True,
        tracked_mp4=True,
        busy=False,
    )

    assert state["compound"] is True
    assert state["auto_import"] is True
    assert state["restart"] is False


def test_button_states_disable_primary_actions_while_busy() -> None:
    state = button_states(
        process=ProcessStatus.RUNNING,
        phase=WorkflowPhase.COMPOSITE_DONE,
        selected_project=True,
        confirmed_open=True,
        tracked_mp4=True,
        busy=True,
    )

    assert all(enabled is False for enabled in state.values())


def test_gui_state_defaults_match_safe_start() -> None:
    state = GuiState()

    assert state.selected_project_path is None
    assert state.opened_project_confirmed is False
    assert state.tracked_mp4_path is None
    assert state.workflow_phase == WorkflowPhase.IDLE
    assert state.busy is False


def test_status_messages_do_not_claim_success() -> None:
    assert format_status_message("compound_sent", "x.mp4") == "已发送复合请求，等待缓存生成..."
    assert format_status_message("restart_ready", None) == "已重启，请打开目标项目"
    assert format_status_message("import_sent", None) == "已发送导入请求，请在剪映中确认"
