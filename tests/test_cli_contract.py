import json
import subprocess
import sys


def test_scan_mp4_failure_outputs_structured_json(tmp_path):
    missing = tmp_path / "missing.mp4"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "jianying_controller",
            "scan",
            "--mp4",
            str(missing),
            "--json",
        ],
        cwd=".",
        capture_output=True,
        text=True,
        timeout=30,
    )

    payload = json.loads(result.stdout)

    assert result.returncode != 0
    assert payload["status"] == "failed"
    assert payload["code"] == "media_not_found"
