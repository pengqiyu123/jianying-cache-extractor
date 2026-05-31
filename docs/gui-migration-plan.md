# GUI 迁移计划：Tkinter → pywebview + Discord 风格深色主题

## Context

当前 GUI 使用 ttkbootstrap "darkly" 主题（`gui.py`，906 行），视觉上限为"Windows 原生控件套层皮"。用户要求 Discord 桌面版风格——圆角、紧凑、无边框感。

**结论**：CustomTkinter 做不到，PyQt6 太重（+50-80MB、GPL 许可证）。**pywebview + HTML/CSS** 是最优解——视觉无上限、启动快、依赖轻（~2MB）、MIT 许可。

**范围**：仅替换前端展示层，后端 15 个模块零改动。

---

## 目标目录结构

```
src/jianying_controller/
  gui.py                    # 删除
  gui/                      # 新建包
    __init__.py             # pywebview 窗口创建 + main() 导出
    api.py                  # PythonApi 类，暴露给 JS 调用
    state.py                # GuiState、button_states、常量（从 gui.py 提取）
  frontend/                 # 新建静态资源
    index.html              # 主页面布局
    style.css               # Discord 深色主题
    app.js                  # 前端交互逻辑
```

---

## 实施步骤

### Step 1：提取纯函数到 `gui/state.py`

从 `gui.py` 中提取**零 Tkinter 依赖**的代码：

- 常量：`APP_TITLE`、`APP_VERSION`、`BADGE_COLORS`、`PROCESS_LABELS`、`REJECTION_LABELS`、`PHASE_LABELS`、`STATUS_MESSAGES`、`USAGE_INSTRUCTIONS`
- 辅助函数：`human_size()`、`human_duration()`、`resolution_label()`、`_classification_display()`、`_classification_tag()`、`_badge_style()`、`_process_tone()`、`_phase_tone()`、`format_status_message()`
- 数据类：`GuiState`
- 纯函数：`button_states()`

这些函数被 `test_gui_cli_contract.py` 测试覆盖，提取后只改 import 路径。

### Step 2：创建 `gui/__init__.py` 入口

```python
def main() -> None:
    import webview
    from pathlib import Path
    from .api import PythonApi

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    window = webview.create_window(
        title="剪映缓存提取工具 v0.1",
        url=str(frontend_dir / "index.html"),
        js_api=PythonApi,  # pywebview 自动实例化并暴露
        min_size=(1000, 780),
        width=1100,
        height=900,
        text_select=True,
        background_color="#313338",
    )
    webview.start(debug=False)
```

**关键细节**：
- `gui.py` 和 `gui/` 包不能共存，先将 `gui.py` 重命名为 `gui/_tk.py`，`__init__.py` 临时 `from ._tk import main`，确保每一步都可回退
- 最终版 `__init__.py` 使用 pywebview

### Step 3：创建 `frontend/index.html`

Discord 风格两栏布局：
- **左侧边栏**（280px）：环境信息（剪映状态/版本/草稿目录）、项目选择下拉框、确认复选框、使用说明折叠区
- **右侧主区**：缓存视频表格、三步操作区（①复合片段 ②重启 ③导入）、草稿创建区、结果卡片
- **底部**：可折叠诊断日志面板

可直接在浏览器中打开验证布局，无需 Python。

### Step 4：创建 `frontend/style.css`

Discord 深色主题色板：

| 变量 | 值 | 用途 |
|------|-----|------|
| `--bg-primary` | `#313338` | 主背景 |
| `--bg-secondary` | `#2B2D31` | 侧边栏背景 |
| `--bg-surface` | `#383A40` | 卡片/输入框背景 |
| `--accent-brand` | `#5865F2` | Discord 蓝紫色 |
| `--accent-green` | `#23A559` | 成功/可用 |
| `--accent-yellow` | `#F0B232` | 警告/忙碌 |
| `--accent-red` | `#DA373C` | 错误 |
| `--radius-md` | `8px` | 圆角 |

关键样式：
- 按钮：`border-radius: 4px`，`transition: background 0.15s`，disabled 时 `opacity: 0.4`
- 卡片：`background: var(--bg-surface)`，`border-radius: 8px`，`border: 1px solid var(--border-default)`
- 表格：紧凑行高，状态列用颜色文字标记（绿色=可用、黄色=写入中、灰色=已拒绝）
- 徽章：与当前 5 种 tone（ok/busy/muted/error/info）一一对应

### Step 5：创建 `gui/api.py`（PythonApi 类）

**通信模式**：
- JS → Python：`pywebview.api.method_name()` 调用
- Python → JS：`window.evaluate_js("window.__onPyEvent(event, payload)")`

**API 方法映射**：

| 方法 | 后端调用 | 返回方式 |
|------|---------|---------|
| `detect_environment()` | `JianYingEnv.detect()` | _emit("env_info") |
| `refresh_projects()` | `detect_recent_drafts()` | _emit("projects") |
| `scan_cache()` | `find_combination_mp4s()` + `inspect_private_cache()` | _emit("scan_result") |
| `compound_clip(hotkey)` | `run_compound_clip_sequence()` | _emit("compound_result") |
| `uncompose_clip()` | `run_uncompose_clip_sequence()` | _emit("uncompose_result") |
| `restart_jianying()` | `restart_jianying_for_import()` | _emit("restart_result") |
| `auto_import()` | `auto_import_file()` | _emit("import_result") |
| `create_draft(name)` | `create_extracted_draft()` / `create_private_cache_draft()` | _emit("draft_created") |
| `select_project(index)` | 更新内部状态 | _emit("button_states") |
| `set_confirmed_open(value)` | 更新内部状态 | _emit("button_states") |
| `get_button_states()` | `button_states()` | 直接 return |
| `start_process_polling()` | 后台线程 3s 轮询 `_process.status()` | _emit("process_status") |
| `open_draft_dir()` | `subprocess.Popen(["explorer", path])` | 无回调 |

**线程安全**：用 `threading.Lock` 保护 `busy` 标志。耗时操作在 `threading.Thread(daemon=True)` 中执行，完成后通过 `_emit()` 推送结果。

### Step 6：创建 `frontend/app.js`

核心逻辑：
1. **初始化**：监听 `pywebviewready` 事件 → 调用 `detect_environment()` + `start_process_polling()`
2. **事件分发**：`window.__onPyEvent(event, payload)` 接收 Python 推送，按 event type 更新 DOM
3. **缓存表格渲染**：`renderCacheTable(files)` 生成表格行，点击行选中并追踪
4. **按钮状态**：`updateButtonStates(states)` 批量更新 disabled 属性
5. **快捷键捕获**：纯 JS 实现（替代 `HotkeyCapture` widget），`keydown` 事件组合修饰键
6. **日志面板**：`addLog(message)` 追加带时间戳的日志，自动滚动

### Step 7：更新 `setup.cfg`

```ini
install_requires =
    pymediainfo
    psutil
    pyJianYingDraft
    pywebview>=5.0
    pyautogui
    pywin32

[options.package_data]
jianying_controller = frontend/*
```

移除 `ttkbootstrap>=1.10`，添加 `pywebview>=5.0` 和 `package_data`。

### Step 8：更新测试 + 清理

- `test_gui_cli_contract.py`：import 改为 `from jianying_controller.gui.state import ...`
- 删除 `gui/_tk.py`（旧 Tkinter 实现）
- 运行 `pytest tests/` 确认全部通过
- 运行 `python -m jianying_controller` 确认 pywebview 窗口正常启动
- 测试 CLI 子命令不受影响

---

## 涉及的关键文件

| 文件 | 操作 |
|------|------|
| `src/jianying_controller/gui.py` | 删除（内容迁移到 gui/ 包） |
| `src/jianying_controller/gui/__init__.py` | 新建 |
| `src/jianying_controller/gui/api.py` | 新建 |
| `src/jianying_controller/gui/state.py` | 新建（从 gui.py 提取） |
| `src/jianying_controller/frontend/index.html` | 新建 |
| `src/jianying_controller/frontend/style.css` | 新建 |
| `src/jianying_controller/frontend/app.js` | 新建 |
| `src/jianying_controller/__main__.py` | 无需改动（`from .gui import main` 仍然有效） |
| `setup.cfg` | 修改依赖和添加 package_data |
| `tests/test_gui_cli_contract.py` | 修改 import 路径 |

---

## 验证方法

1. **Step 1 后**：`pytest tests/test_gui_cli_contract.py` 通过
2. **Step 3-4 后**：浏览器直接打开 `index.html`，验证布局和主题
3. **Step 5-6 后**：`python -m jianying_controller` 启动 pywebview 窗口，验证功能
4. **Step 7 后**：`pip install -e .` + `python -m jianying_controller` 验证打包安装
5. **Step 8 后**：`pytest tests/` 全部通过 + CLI 子命令正常
