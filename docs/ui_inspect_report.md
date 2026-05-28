# JianYing Pro v10.6 UI 元素探测报告

## 结论

**阻塞：剪映 v10.6.0.14057 没有向 Windows UI Automation 暴露首页内部控件。**

本次用 UIA Control View、UIA Raw View、Win32 子窗口枚举、MSAA/oleacc 四种方式交叉探测，均只能看到顶层窗口，不能读取草稿卡片、导航、导出按钮、时间轴等内部元素。因此目前不能给出可直接定位导出按钮的 `uiautomation` 选择器；继续沿用旧版 `HomePageDraftTitle` / `MainWindowTitleBarExportBtn` 方案在 v10.6 上不可行。

## 探测说明
- 本次探测使用 Python `uiautomation`，只读取 UI 树。
- 未点击导出、删除、确认、发布等风险按钮。
- 编辑界面进入状态：未尝试打开草稿。

## 环境信息
```text
JianYing Pro v10 (10.6.0.14057)
  Install:   C:\Users\pengq\AppData\Local\JianyingPro
  EXE:       C:\Users\pengq\AppData\Local\JianyingPro\Apps\10.6.0.14057\JianyingPro.exe
  Launcher:  C:\Users\pengq\AppData\Local\JianyingPro\Apps\JianyingPro.exe
  Drafts:    C:\Users\pengq\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft
  UserData:  C:\Users\pengq\AppData\Local\JianyingPro\User Data
  FFmpeg:    C:\Users\pengq\AppData\Local\JianyingPro\Apps\10.6.0.14057\ffmpeg.exe
  Tray:      C:\Users\pengq\AppData\Local\JianyingPro\Apps\10.6.0.14057\JianyingProTray.exe
  Drafts:    47 projects found
             (42 encrypted)
```

## 窗口信息
- 窗口标题：剪映专业版
- ClassName：HomePage_QMLTYPE_181
- 位置和大小：550,203,2010,1178

## 探测结果概览
- UIA Control View 首页节点数：1
- UIA Raw View 首页节点数：1
- Win32 子窗口数：0
- MSAA/oleacc 节点数：1

说明：如果以上树都只暴露顶层窗口或极少节点，说明剪映 v10.6 的 Qt/QML 渲染界面没有向 Windows UI Automation 暴露内部按钮文本，不能直接用旧版 `HomePageDraftTitle`、`MainWindowTitleBarExportBtn` 一类选择器。

补充验证：`JianYingProcess.open_draft('11月10日')` 返回成功，但实际打开的是 Windows 文件资源管理器中的草稿目录，不是剪映编辑界面，因此不能作为进入编辑页的自动化入口。

## 首页 - 关键交互元素

| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |
|------|-------------|------|--------------|-----------|----------|
| #0 `0` | WindowControl | 剪映专业版 | HomeWindow | HomePage_QMLTYPE_181 | 首页导航 |

## 编辑界面 - 关键交互元素

| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |
|------|-------------|------|--------------|-----------|----------|

## 导出对话框 - 关键交互元素（如果能进入）

未进入导出对话框。按照任务安全要求，本次只做只读探测，不点击导出按钮。

## 选择器速查（供自动化使用）

```python
import uiautomation as uia

window = uia.WindowControl(searchDepth=1, Name='剪映专业版')
if not window.Exists(1):
    window = uia.WindowControl(searchDepth=1, Compare=lambda c, d: '剪映' in c.Name or 'Jianying' in c.Name or 'Jianying' in c.ClassName)

# 首页
draft_list_or_card = None  # not found
export_button = None  # not found
timeline_area = None  # not found
play_control = None  # not found
media_panel = None  # not found
text_panel = None  # not found

# 编辑界面
draft_list_or_card = None  # not found
export_button = None  # not found
timeline_area = None  # not found
play_control = None  # not found
media_panel = None  # not found
text_panel = None  # not found
```

## 下一步建议
- 方案 A：改用图像识别/坐标自动化。先固定剪映窗口尺寸，截图定位按钮区域，再用 `pyautogui` 执行受控点击。
- 方案 B：查找 Qt Accessibility 开关。若剪映随 Qt 提供可访问性插件，尝试通过环境变量或启动参数开启内部控件树后重跑本脚本。
- 方案 C：降级使用已知支持 UIA 选择器的剪映 5.9/6.x 做自动导出，v10.6 只做草稿生成和人工导出。
- 方案 D：继续研究本地协议/命令行入口，但不要把草稿文件夹打开误判为剪映编辑页打开。

## 原始数据
- 完整 UI 树：`docs/ui_tree_full.txt`
- 首页节点数：1
- 首页 Raw View 节点数：1
- Win32 子窗口数：0
- MSAA 节点数：1
- 编辑界面节点数：0