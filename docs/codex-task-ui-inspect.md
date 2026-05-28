# Codex Task: JianYing Pro v10.6 UI 元素探测

## 目标

用 Python `uiautomation` 库探测剪映专业版 v10.6 的主窗口 UI 结构，抓取首页（草稿列表页）的所有可识别元素，输出结构化报告。

## 环境信息

- 剪映版本：v10.6.0.14057
- 安装路径：`C:\Users\pengq\AppData\Local\JianyingPro\Apps\10.6.0.14057\JianyingPro.exe`
- 启动器：`C:\Users\pengq\AppData\Local\JianyingPro\Apps\JianyingPro.exe`
- Python 已有模块：`jianying_controller`（在 `src/jianying_controller/`）
- 需要安装：`pip install uiautomation`
- 工作目录：`D:\python\JianYingPro`

## 执行步骤

### Step 1: 安装依赖

```bash
pip install uiautomation
```

### Step 2: 启动剪映

用已有的控制器启动剪映并等待就绪：

```python
import sys
sys.path.insert(0, "src")
from jianying_controller import JianYingEnv, JianYingProcess

env = JianYingEnv()
proc = JianYingProcess(env)
proc.launch(wait=True, timeout=30)
```

### Step 3: 抓取 UI 树

编写 `scripts/ui_inspect.py`，核心逻辑：

1. 用 `uiautomation.WindowControl` 搜索剪映主窗口
   - 搜索条件：`Name` 包含 "剪映" 或 "JianyingPro"
   - 备选：`ClassName` 搜索
2. 遍历 UI 树（深度控制在 8-10 层），收集以下信息：
   - `ControlType`（按钮、文本、列表项、面板等）
   - `Name`（显示文本）
   - `AutomationId`
   - `ClassName`
   - `BoundingRectangle`（位置和大小）
   - `IsEnabled`、`IsOffscreen`
3. 特别关注并标记这些关键区域：
   - 顶部标题栏（导出按钮、撤销/重做、项目名称）
   - 左侧导航栏（首页、模板、创作等 tab）
   - 中间草稿列表（每个草稿卡片的标题、封面、时间）
   - 右侧面板（如果有的话）
   - 底部状态栏
4. 输出两层报告：
   - **精简版**：只列出有 `Name` 或 `AutomationId` 的关键交互元素（按钮、菜单项、输入框）
   - **完整版**：保存到文件 `docs/ui_tree_full.txt`，包含完整树结构

### Step 4: 打开一个草稿后再探测

1. 用代码模拟点击第一个草稿打开它（或用 `proc.open_draft()`)
2. 进入编辑界面后，再次抓取 UI 树
3. 重点关注编辑界面的：
   - 导出按钮位置和选择器
   - 时间轴区域
   - 播放控制区
   - 属性面板

### Step 5: 输出报告

将结果保存到 `docs/ui_inspect_report.md`，格式如下：

```markdown
# JianYing Pro v10.6 UI 元素探测报告

## 窗口信息
- 窗口标题：xxx
- ClassName：xxx
- 位置和大小：xxx

## 首页 - 关键交互元素

| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |
|------|------------|------|-------------|-----------|---------|
| ... | Button | "导出" | ... | ... | 导出按钮 |

## 编辑界面 - 关键交互元素

| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |
|------|------------|------|-------------|-----------|---------|

## 导出对话框 - 关键交互元素（如果能进入）

| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |
|------|------------|------|-------------|-----------|---------|

## 选择器速查（供自动化使用）

```python
# 首页草稿列表
home_draft_list = window.xxx

# 导出按钮
export_btn = window.xxx

# 导出对话框 - 分辨率选择
resolution_selector = window.xxx

# 导出对话框 - 确认按钮
export_confirm_btn = window.xxx
```
```

## 注意事项

1. **不要操作任何按钮**，只读取 UI 信息，特别是不要点导出、删除等危险操作
2. 剪映主窗口加载需要时间，搜索窗口前先 sleep 5-10 秒
3. 如果 `uiautomation` 找不到窗口，尝试用 `ClassName` 搜索（剪映可能用 Chromium/Electron 框架，ClassName 可能是 `Chrome_WidgetWin_0` 或类似）
4. 如果 UI 树太深（超过 10 层），只记录前 10 层
5. 导出完剪映不需要退出，保持运行状态即可
6. 所有输出文件放到 `docs/` 目录下

## 验收标准

- [ ] `docs/ui_inspect_report.md` 存在且内容完整
- [ ] 报告包含首页至少 10 个有意义的交互元素
- [ ] 报告包含编辑界面至少 5 个有意义的交互元素
- [ ] 提供了可直接用于自动化的 Python 选择器代码
- [ ] 剪映未被关闭，保持运行状态
