from jianying_controller.process import JianYingProcess, ProcessStatus


def test_status_reports_background_when_main_process_has_no_visible_window(monkeypatch):
    process = JianYingProcess()

    monkeypatch.setattr(process, "_process_ids", lambda image_name: [123] if image_name == "JianyingPro.exe" else [])
    monkeypatch.setattr(process, "_has_visible_window", lambda process_ids: False)

    assert process.status() == ProcessStatus.BACKGROUND


def test_status_reports_running_only_when_main_window_is_visible(monkeypatch):
    process = JianYingProcess()

    monkeypatch.setattr(process, "_process_ids", lambda image_name: [123] if image_name == "JianyingPro.exe" else [])
    monkeypatch.setattr(process, "_has_visible_window", lambda process_ids: True)

    assert process.status() == ProcessStatus.RUNNING


def test_status_reports_tray_only_without_main_process(monkeypatch):
    process = JianYingProcess()

    def fake_process_ids(image_name):
        return [456] if image_name == "JianyingProTray.exe" else []

    monkeypatch.setattr(process, "_process_ids", fake_process_ids)
    monkeypatch.setattr(process, "_has_visible_window", lambda process_ids: False)

    assert process.status() == ProcessStatus.TRAY_ONLY
