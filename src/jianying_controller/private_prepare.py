"""Prepare JianYing for importing a refreshed private cache."""

from __future__ import annotations

from .models import CreateDraftResult, ProcessStatus
from .process import JianYingProcess


def restart_jianying_for_import(*, process=None) -> CreateDraftResult:
    process = process or JianYingProcess()
    status = process.restart_jianying()
    if status != ProcessStatus.RUNNING:
        return CreateDraftResult(status="restart_failed", warnings=[f"剪映重启未完成: {status}"])
    return CreateDraftResult(status="ready_for_manual_import", warnings=["已重启，请打开目标项目"])
