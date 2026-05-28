# Codex Task: GUI 打磨与端到端验收

## 背景

你正在为「剪映缓存提取器」项目工作。这是一个 Windows 桌面工具，帮助用户从剪映专业版 v10.6 中提取复合片段预合成缓存，并自动创建可识别的新草稿。

**项目路径**：`D:\python\JianYingPro`
**工作目录**：`D:\python\JianYingPro`（所有操作在此目录下执行）

## 当前状态

服务层和 CLI 已全部完成并通过测试：

```
src/jianying_controller/
  models.py           # 统一数据模型（SourceMode, CacheOrigin, MediaCandidate, CreateDraftRequest, CreateDraftResult, WorkflowError）
  media_validator.py   # 视频轨校验、文件稳定性、复制校验
  source_resolver.py   # 三种来源统一解析（auto/project/mp4）
  workflow.py          # scan_source() / create_draft_from_source() 主流程
  draft_creator.py     # 创建新草稿（含回滚、唯一命名、size 校验）
  cache_extractor.py   # 扫描 Resources/combination/
  project_detector.py  # 检测活跃项目（支持 .cloud_cache_* 镜像）
  env.py               # 环境探测（安装路径、版本、草稿目录）
  process.py           # 进程管理（启动、退出、状态检测）
  gui.py               # tkinter GUI（已有三模式初版）
  __main__.py          # CLI 入口（scan/create --auto/--project/--mp4 --json）
  __init__.py          # 导出
```

测试：`python -m pytest tests -q --basetemp .pytest_tmp` → 16 passed

CLI 已验证：`python -m jianying_controller scan --auto --json` 能正确检测到 `5月28日 (1)-副本` 的 cloud_cache 有效 MP4（116MB, 1920x1080, 124s）。

## 当前 GUI 状态

`gui.py` 已有三模式界面初版，包含：
- 顶部状态栏（剪映状态、草稿目录、来源、状态）
- 三模式切换（自动识别 / 选择项目 / 选择 MP4）
- 来源区（三种模式对应的输入控件）
- 候选列表（Treeview，显示文件名、来源、大小、时长、分辨率、修改时间、状态、路径）
- 操作按钮（重新检测、生成草稿、打开草稿目录、我已确认可打开）
- 日志区
- 后台线程执行 scan 和 create，不阻塞 UI

## 你的任务

### 1. 运行 GUI 并端到端验收

启动 GUI：
```bash
cd D:\python\JianYingPro
python -m jianying_controller
```

验证以下场景：

**场景 A：自动识别模式**
1. GUI 启动后默认是「自动识别」模式
2. 剪映应正在运行（如未运行，用 `python -c "import sys; sys.path.insert(0,'src'); from jianying_controller import JianYingEnv, JianYingProcess; proc=JianYingProcess(JianYingEnv()); proc.launch(wait=True, timeout=30)"` 启动）
3. 自动检测应显示「5月28日 (1)-副本」作为来源
4. 候选列表应显示至少 1 个 `可用` 的 MP4（116MB, cloud_cache 镜像来源）
5. 点击「生成草稿」应成功创建新草稿
6. 点击「打开草稿目录」应打开文件资源管理器
7. 状态应显示「草稿已创建，请回到剪映首页查看。」

**场景 B：选择项目模式**
1. 切换到「选择项目」
2. 选择一个草稿项目目录（如 `C:\Users\pengq\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft\5月28日 (1)-副本`）
3. 应能扫描出相同的 cloud_cache MP4

**场景 C：选择 MP4 模式**
1. 切换到「选择 MP4」
2. 选择一个有效 MP4 文件
3. 应能验证并创建草稿

### 2. 修复发现的问题

验收过程中如果发现任何 bug、UI 异常或逻辑错误，直接修复。常见问题可能包括：
- 候选列表没有自动选中第一个可用项
- 按钮状态不正确（应该 disabled 的时候 enabled 了，或反之）
- 日志信息不够清晰
- 窗口大小或布局问题
- 线程安全问题

### 3. 打磨 GUI 体验

在现有代码基础上改进（不要重写，在现有结构上迭代）：

- **空状态提示**：当检测不到项目、找不到缓存时，显示友好提示文案（参照软件策划文档第 4 节的空状态文案表）
- **候选列表排序**：可用排在前面，被拒绝的排在后面
- **来源标签颜色**：可用项用绿色标签，被拒绝项用灰色
- **进度反馈**：扫描和创建过程中，按钮显示禁用状态并更新状态文字
- **错误处理**：所有 WorkflowError 友好展示，不暴露 Python 堆栈给用户
- **窗口标题**：显示版本信息，如「剪映缓存提取 v0.1」

### 4. 运行测试确认无回归

```bash
python -m pytest tests -q --basetemp .pytest_tmp
```

所有 16 个测试必须通过。

### 5. 清理测试草稿

如果验收过程中创建了新的测试草稿，清理掉（只保留第一次验证时创建的 `提取_5月28日 (1)-副本_20260528_210210` 作为参考）。

## 重要约束

1. **不要修改 `workflow.py`、`source_resolver.py`、`media_validator.py`、`models.py`** — 这些模块已验证稳定，只改 `gui.py`
2. **不要出现「导出成功」「自动导出」等误导文案** — 详见策划文档禁止文案清单
3. **GUI 和 CLI 必须调用同一套 workflow** — gui.py 只调用 workflow.py 的函数
4. **剪映正在运行时不要退出它** — 保持当前运行状态
5. **不要删除任何已有草稿** — 只读访问原项目目录
6. **测试用 `--basetemp .pytest_tmp`** — 默认 tmp 目录有权限问题
7. **Python 版本是 3.11**（`C:\Users\pengq\AppData\Local\Programs\Python\Python311\python.exe`）

## 验收标准

- [ ] GUI 三模式均可正常操作
- [ ] 自动识别模式能正确检测到 `5月28日 (1)-副本` 的 cloud_cache MP4
- [ ] 点击「生成草稿」能成功创建新草稿
- [ ] 点击「打开草稿目录」能打开文件资源管理器
- [ ] 空状态有友好提示
- [ ] 没有 Python 堆栈暴露给用户
- [ ] 16 个测试全部通过
- [ ] 没有出现「导出成功」等禁止文案
