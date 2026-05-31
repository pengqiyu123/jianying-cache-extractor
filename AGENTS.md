# JianYing Cache Extractor Notes

- `D:\python\JianYingPro\PLAN.md` 是本项目唯一执行蓝图。
- 第一版只做 Python CLI + Tkinter GUI。
- 不添加 Electron、Node、Playwright、JSONL action runner、打包流程。
- 复合片段默认快捷键是 `shift+g`。
- 重启只关闭 `JianyingPro.exe` 主进程，保留 `JianyingProTray.exe`。
- 一键导入只用 Win32 导入对话框，不使用剪贴板。
- 私有缓存主 MP4 不用 MediaInfo 解析；允许使用 `.alpha.mp4` 推断尺寸和时长。
