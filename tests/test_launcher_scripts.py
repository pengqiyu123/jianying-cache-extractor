from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_files_exist():
    for relative_path in ("start.bat", "stop.bat", "scripts/start.ps1", "scripts/stop.ps1"):
        assert (ROOT / relative_path).is_file()


def test_stop_script_targets_only_recorded_tool_process():
    stop_script = (ROOT / "scripts" / "stop.ps1").read_text(encoding="utf-8")

    assert "JianyingPro.exe" not in stop_script
    assert "JianyingProTray.exe" not in stop_script
    assert ".run" in stop_script
    assert "jianying_controller" in stop_script


def test_start_script_records_pid_and_launches_gui_module():
    start_script = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")

    assert ".run" in start_script
    assert "jianying-cache-extractor.pid" in start_script
    assert "-m" in start_script
    assert "jianying_controller" in start_script
    assert "pythonw.exe" in start_script
    assert 'Start-Process `\n    -FilePath $GuiPython' in start_script
