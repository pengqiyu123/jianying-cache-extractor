# 剪映缓存提取工具

Python CLI + Tkinter GUI，用于按三步流程搬运剪映复合片段缓存：

1. 一键复合片段：聚焦剪映后发送 `Ctrl+A -> Alt+G -> Ctrl+A -> Shift+G`。
2. 重启剪映：只关闭 `JianyingPro.exe` 主进程，保留 `JianyingProTray.exe`。
3. 一键导入：聚焦剪映后用 `Ctrl+I` 打开系统导入对话框，写入 MP4 路径并点击打开。

第一版不包含 Electron、Node、Playwright、JSONL runner 或打包流程。

## 使用

```powershell
python -m pip install -e .
python -m jianying_controller
```

CLI：

```powershell
python -m jianying_controller scan --auto
python -m jianying_controller scan --project <path>
python -m jianying_controller scan --mp4 <path>
python -m jianying_controller create --auto
python -m jianying_controller auto-import <mp4>
python -m jianying_controller compound-clip --hotkey shift+g
python -m jianying_controller prepare-import <mp4>
python -m jianying_controller uncompose-clip
```

## 硬约束

- 不使用 UIA/pywinauto 操作剪映内部控件。
- 重启导入流程不杀托盘。
- 一键导入不使用剪贴板。
- 操作文案只表示“已发送请求”，不承诺剪映内部动作成功。
