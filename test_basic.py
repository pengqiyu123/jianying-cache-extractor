"""Quick smoke test for JianYing controller basics."""

import sys
sys.path.insert(0, "src")

from jianying_controller import JianYingEnv, JianYingProcess
from jianying_controller.process import ProcessStatus

def main():
    print("=" * 60)
    print("JianYing Pro Controller - Environment Detection")
    print("=" * 60)

    # 1. Detect environment
    env = JianYingEnv()
    info = env.detect()
    print(env.summary())

    # 2. Check process status
    print("\n" + "=" * 60)
    print("Process Status")
    print("=" * 60)
    proc = JianYingProcess(env)
    status = proc.status()
    print(f"  Status: {status.value}")

    # 3. List drafts (first 10)
    print("\n" + "=" * 60)
    print("Existing Drafts (first 10)")
    print("=" * 60)
    drafts = env.list_drafts()[:10]
    for d in drafts:
        enc = "ENCRYPTED" if d.get("content_encrypted") else "plain"
        size_kb = d["content_size"] / 1024
        print(f"  [{enc:>9}] {size_kb:>8.1f} KB  {d['name']}")
    total = len(env.list_drafts())
    if total > 10:
        print(f"  ... and {total - 10} more")
    print(f"  Total: {total} drafts")

    # 4. Quick process control test (just status, don't actually launch/kill)
    print("\n" + "=" * 60)
    print("Process Control Available")
    print("=" * 60)
    print(f"  Launch EXE:  {info.launcher_path}")
    print(f"  Main EXE:    {info.exe_path}")
    print(f"  FFmpeg:      {info.ffmpeg_path or 'not found'}")
    print(f"  Can launch:  {info.launcher_path.exists()}")
    print(f"  Can export:  {'maybe (v10.6 - UI automation untested)' if info.version else 'no'}")


if __name__ == "__main__":
    main()
