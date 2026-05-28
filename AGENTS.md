# JianYing Pro Automation — AGENTS.md

> 项目状态：基础控制器已搭建，环境探测和进程管理已验证通过。

## 本地环境实测数据

| 项目 | 值 |
|------|-----|
| 剪映版本 | **v10.6.0.14057**（ByteDance, 2026） |
| 安装路径 | `C:\Users\pengq\AppData\Local\JianyingPro` |
| 主程序 | `Apps\10.6.0.14057\JianyingPro.exe` |
| 启动器 | `Apps\JianyingPro.exe`（自动定位最新版本） |
| 草稿目录 | `User Data\Projects\com.lveditor.draft\` |
| 托盘程序 | `Apps\10.6.0.14057\JianyingProTray.exe` |
| FFmpeg | `Apps\10.6.0.14057\ffmpeg.exe`（剪映自带） |
| 草稿总数 | 47 个（42 个已加密，5 个明文为系统缓存） |

## 已验证的技术结论

### 1. 草稿加密

剪映 v10.6 的 `draft_content.json` 和 `draft_meta_info.json` **全部加密**（Base64 编码的二进制数据，非 JSON）。

**影响**：
- pyJianYingDraft 的**模板模式不可用**（需要读取已有草稿作为模板）
- pyJianYingDraft 的**草稿生成仍然可用**（它创建明文 JSON，剪映可读取）
- `draft.extra` 也是加密的
- `.bak` 文件同样加密

**验证方式**：读取文件首字符，如果不是 `{` 或 `[` 则判定为加密。

### 2. 进程控制

| 操作 | 方法 | 结果 |
|------|------|------|
| 启动 | `subprocess.Popen` 启动 launcher | **成功**，约 15-20 秒就绪 |
| 优雅退出 | `taskkill /IM JianyingPro.exe`（无 /F） | **失败**，剪映忽略 WM_CLOSE |
| 强制退出 | `taskkill /F /IM JianyingPro.exe` | **成功** |
| 退出托盘 | `taskkill /IM JianyingProTray.exe` | **成功**（仅托盘模式下可优雅退出） |

**结论**：退出流程必须先尝试优雅 → 失败后自动回退到 `taskkill /F`，同时清理主进程和托盘进程。

### 3. 进程状态三态

```
STOPPED    — 无任何剪映进程
RUNNING    — JianyingPro.exe 主进程运行中
TRAY_ONLY  — 仅 JianyingProTray.exe 托盘在后台
```

### 4. UI 自动化导出 — 已确认不可用

pyJianYingDraft 的 `JianyingController.export_draft()` 基于 `uiautomation` 库，通过窗口标题和控件名称定位 UI 元素。

**Codex 四路交叉探测结果**（2026-05-28）：

| 探测方式 | 首页节点数 | 说明 |
|---------|-----------|------|
| UIA Control View | 1 | 仅顶层窗口 |
| UIA Raw View | 1 | 仅顶层窗口 |
| Win32 子窗口枚举 | 0 | 无子窗口 |
| MSAA/oleacc | 1 | 仅顶层窗口 |

**窗口信息**：标题 `剪映专业版`，ClassName `HomePage_QMLTYPE_181`（Qt/QML 渲染）

**结论**：剪映 v10.6 使用 Qt/QML 自绘界面，**不向 Windows UI Automation 暴露任何内部控件**。旧版 `HomePageDraftTitle` / `MainWindowTitleBarExportBtn` 等选择器完全失效。无法通过 UIA 获取草稿卡片、导出按钮、时间轴等任何交互元素。

**补充发现**：`proc.open_draft("草稿名")` 实际只打开了 Windows 文件资源管理器中的草稿目录，并非剪映编辑界面。

**探测脚本**：`scripts/ui_inspect.py`（可重复运行）
**完整报告**：`docs/ui_inspect_report.md`
**原始数据**：`docs/ui_tree_full.txt`

### 5. 复合片段缓存提取 — 可用的无损导出路径

**核心原理**：利用剪映的"预合成复合片段"机制，绕过 VIP 导出限制，直接从本地缓存提取渲染后的视频。

**完整流程**：

```
1. 在剪映编辑界面全选时间线素材 (Ctrl+A)
2. 右键 → 新建复合片段 (Alt+G)
3. 右键复合片段 → 预合成复合片段
4. 剪映后台渲染，生成缓存 MP4 到：
   <草稿目录>/<项目名>/Resources/combination/<UUID>_video.mp4
5. 直接复制该 MP4 即为无损成品
```

**本地验证**（2026-05-28）：

| 路径 | 文件 | 大小 |
|------|------|------|
| `5月28日 (1)-副本/Resources/combination/` | `05E15BF9-..._video.mp4` | **116 MB**（有效缓存） |
| `1月14日/Resources/combination/` | 多个 UUID 文件 | 0 MB（空壳，已被清理） |

**缓存文件命名规则**：
- `{UUID}_video.mp4` — 主视频缓存
- `{UUID}_video.mp4.alpha.mp4` — 透明通道缓存（如有）

**关键注意事项**：
- 不要关闭剪映，否则临时文件可能被清理
- 预合成视频仅一次性有效，复制后需妥善保存
- 缓存文件包含所有特效/滤镜/转场/字幕的最终渲染结果

**自动化可行性**：
- **草稿生成**：pyJianYingDraft 可编程创建草稿（视频/音频/文本/特效）✅
- **复合片段创建**：需要在剪映 GUI 中手动操作（UIA 封闭，无法自动化）⚠️
- **缓存提取**：纯文件系统操作，可完全自动化 ✅
- **拖入编辑界面导出**：需要 GUI 操作 ⚠️

**参考资料**：
- [剪映9.0 VIP导出mp4文件夹 — CSDN](https://blog.csdn.net/namekong8/article/details/151753824)
- [免费使用剪映全部功能并导出高清视频 — 独特吧](https://www.dute8.cn/jnmfsyjyqbgnbdcgqsb-wxvjsjygnbsygjgndsyjq.html)
- [剪映专业版v9.4 不登录可导出VIP素材 — 数码之家](https://www.mydigit.cn/thread-566665-1-1.html)
- [畅享剪映全功能无需登录 — 知乎](https://zhuanlan.zhihu.com/p/1943663836235298286)

## 项目结构

```
d:\python\JianYingPro\
├── src\jianying_controller\          # 自研控制器
│   ├── __init__.py                   # 导出 JianYingEnv, JianYingProcess
│   ├── env.py                        # 环境探测：安装路径、版本、草稿目录
│   └── process.py                    # 进程管理：启动、退出、状态检测
├── process\                          # 开源参考项目（只读参考，不直接依赖）
│   ├── pyJianYingDraft\              # 核心 SDK — 草稿生成引擎
│   ├── pyCapCut\                     # CapCut 版本（API 同源）
│   ├── capcut-mate\                  # FastAPI 服务层参考
│   ├── jianying-protocol-service\    # HTTP API 协议参考
│   ├── jianying-editor-skill\        # 工作流编排 + auto_exporter 参考
│   └── JianYingSrt\                  # 字幕自动化（历史参考）
├── scripts\
│   └── ui_inspect.py                 # Codex: UI 元素只读探测脚本
├── docs\
│   ├── jianying-automation-research.md  # Codex 调研报告
│   ├── codex-task-ui-inspect.md         # Codex 任务描述
│   ├── ui_inspect_report.md             # UI 探测结果报告
│   └── ui_tree_full.txt                 # UI 树原始数据
├── test_basic.py                     # 基础功能冒烟测试
└── AGENTS.md                         # 本文件
```

## 架构决策

### ADR-001: 草稿生成用 pyJianYingDraft，不自己写

- **决策**：直接依赖 `pyJianYingDraft`（`pip install pyJianYingDraft`）作为草稿生成引擎
- **原因**：它已实现完整的视频/音频/文本/特效/转场/关键帧支持，API 设计清晰
- **限制**：模板模式在 v10.6 不可用；导出自动化需要重新适配

### ADR-002: 进程控制自建，不依赖 pyJianYingDraft 的 JianyingController

- **决策**：自建 `JianYingProcess` 管理启动/退出
- **原因**：
  - `JianyingController` 的启动逻辑绑定了导出流程
  - v10.6 的 UI 自动化选择器全部失效，无法复用其导出逻辑
  - 我们需要独立控制启动/退出，不依赖 UI 自动化
- **结果**：`JianYingProcess` 已验证可用

### ADR-003: 导出方案 — 复合片段缓存提取路线

- **已排除**：UI Automation 方案（v10.6 不暴露内部控件）
- **选定路线**：复合片段缓存提取
- **流程**：pyJianYingDraft 生成草稿 → 用户在剪映中创建复合片段并预合成 → 自动提取 `Resources/combination/*.mp4`
- **优势**：无损、不依赖 UIA、纯文件系统操作可自动化提取步骤
- **局限**：创建复合片段和预合成仍需用户在剪映 GUI 中手动操作
- **自动化目标**：草稿生成 + 缓存提取全自动，复合片段创建半自动（用户手动一步）

## 已验证的 API

### JianYingEnv

```python
from jianying_controller import JianYingEnv

env = JianYingEnv()            # 自动探测安装路径
info = env.detect()            # 返回 JianYingInfo 数据类
print(env.summary())           # 人类可读的环境摘要

env.list_drafts()              # 列出所有草稿（名称、大小、加密状态）
```

### JianYingProcess

```python
from jianying_controller import JianYingProcess, JianYingEnv

proc = JianYingProcess(env)
proc.status()                  # → STOPPED / RUNNING / TRAY_ONLY
proc.launch(wait=True)         # 启动剪映，等待就绪
proc.exit(force=False)         # 退出（先优雅，失败自动 force）
proc.exit(force=True)          # 强制退出
proc.open_draft("草稿名")      # 打开指定草稿
```

## 参考项目索引

| 项目 | 技术方案 | 本项目中的角色 |
|------|---------|--------------|
| pyJianYingDraft | Python SDK | **草稿生成引擎**，直接依赖 |
| pyCapCut | Python SDK | CapCut 国际版参考 |
| capcut-mate | FastAPI | API 设计参考 |
| jianying-protocol-service | FastAPI | 任务生命周期参考 |
| jianying-editor-skill | Mixin 架构 | 工作流编排 + auto_exporter 参考 |
| JianYingSrt | Python | 字幕处理历史参考 |

## 下一步

1. **验证草稿生成**：用 pyJianYingDraft 创建一个测试草稿，确认 v10.6 能识别并打开
2. **~~UI 自动化导出探索~~** → 已验证不可行（UIA 完全封闭）
3. **缓存提取模块**：实现自动监控 `Resources/combination/` 目录，检测预合成完成后提取 MP4
4. **DraftService 封装**：在 env + process 基础上封装高层草稿操作（创建、添加素材、保存）
5. **半自动导出工作流**：草稿生成(自动) → 复合片段预合成(手动) → 缓存提取(自动)
6. **CLI 入口**：`python -m jianying_controller create/export/status`

## 风险备忘

- **版本漂移**：剪映每次更新可能改变草稿格式和 UI 结构
- **加密升级**：未来版本可能对生成的明文草稿也做加密校验
- **导出脆弱性**：弹窗、登录、VIP 限制、更新提示都会中断 UI 自动化
- **许可合规**：各开源项目许可不同，合并代码前需检查
