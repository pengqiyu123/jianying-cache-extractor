from __future__ import annotations

from pathlib import Path

from jianying_controller.models import ProcessStatus
from jianying_controller.private_prepare import restart_jianying_for_import


class FakeProcess:
    def __init__(self):
        self.called = False

    def restart_jianying(self):
        self.called = True
        return ProcessStatus.RUNNING


def test_restart_jianying_for_import_only_restarts_process() -> None:
    process = FakeProcess()

    result = restart_jianying_for_import(process=process)

    assert process.called is True
    assert result.status == "ready_for_manual_import"
    assert result.tracked_mp4 is None
    assert result.warnings == ["已重启，请打开目标项目"]
