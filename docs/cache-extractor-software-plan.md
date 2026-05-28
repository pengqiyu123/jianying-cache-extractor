# 剪映复合片段缓存提取器软件策划

日期：2026-05-28  
状态：产品策划 / 架构方案 / 交付计划

## 0. 设计团队结论

本轮按产品、后端架构、质量审计、项目交付四个视角评审，结论一致：

**这个软件不应定位为“剪映自动化控制器”或“自动导出工具”，而应定位为“剪映复合片段缓存提取器”。**

它的核心价值是：用户在剪映里完成复合片段预合成后，软件自动或手动定位本地生成的有效 MP4 缓存，复制保护该视频，并创建一个剪映专业版 v10.6 可以识别的新草稿。用户回到剪映草稿箱确认可见、可打开、可播放，再继续手动导出或二次编辑。

已验证的关键事实：

- 剪映 v10.6.0.14057 的 Qt/QML 界面不向 Windows UI Automation 暴露内部控件，不能可靠自动点击导出按钮。
- 复合片段预合成缓存可能出现在原项目 `Resources/combination/`，也可能出现在 `.cloud_cache_*` 镜像目录。
- `.mp4` 后缀不代表文件可导入；必须检测视频轨、分辨率、时长和文件稳定性。
- 用户已确认新草稿 `提取_5月28日 (1)-副本_20260528_210210` 在剪映草稿箱可见，说明“缓存 MP4 -> 新草稿”链路已打通。

## 1. 产品定位

产品名暂定：**剪映缓存提取**

一句话说明：  
**把剪映复合片段预合成生成的本地视频缓存，转成一个新的剪映草稿。**

用户可见承诺：

- 自动推荐当前最可能活跃的项目。
- 支持手动选择项目目录。
- 支持手动选择任意本地 MP4。
- 展示候选视频的来源、大小、时长、分辨率、修改时间和可用状态。
- 复制有效视频到新草稿目录。
- 创建剪映可识别的新草稿。
- 明确提示用户回到剪映确认。

绝不承诺：

- 不承诺自动控制剪映编辑界面。
- 不承诺自动导出。
- 不承诺破解会员限制。
- 不读取或解密加密草稿。
- 不修改原项目。
- 不删除原缓存。
- 不把“草稿已创建”说成“视频已导出成功”。

## 2. 能力目标

### MVP 能力

1. 自动识别当前最可能活跃的剪映项目。
2. 自动关联项目本体和 `.cloud_cache_*` 镜像缓存。
3. 手动选择剪映项目目录并扫描候选缓存。
4. 手动选择任意本地 MP4 并创建新草稿。
5. 候选列表显示文件名、来源、大小、修改时间、分辨率、时长和状态。
6. 复制缓存 MP4 到新草稿资源目录。
7. 使用 `pyJianYingDraft` 创建只包含该 MP4 的新草稿。
8. 显示真实状态：已检测、已复制、草稿已创建、等待用户确认。
9. 支持用户点击确认：`我已在剪映确认可见/可打开`。
10. 提供基础 CLI，方便调试、自动化测试和后续 GUI 调用。

### v0.2 增强能力

1. 文件稳定性实时监控，等待缓存写入完成。
2. 复制后 size + SHA-256 校验。
3. 结构化日志和一键复制诊断信息。
4. 多 `.cloud_cache_*` 镜像评分和冲突提示。
5. PyInstaller `--onedir` 打包为 Windows portable 工具。

## 3. 用户旅程

### 自动识别模式

1. 用户在剪映中打开项目。
2. 用户在剪映中创建复合片段并执行预合成。
3. 用户打开工具，默认进入 `自动识别`。
4. 工具显示剪映状态、推荐项目、推荐原因和候选缓存。
5. 用户选中候选缓存，确认草稿名。
6. 用户点击 `生成草稿`。
7. 工具依次显示：检测中、复制中、创建草稿中、等待剪映确认。
8. 完成后显示：`草稿已创建，请回到剪映首页查看`。
9. 用户在剪映确认后，可在工具里点击 `我已确认可打开`。

推荐原因必须可解释，例如：

- 最近修改的项目。
- 命中 `.cloud_cache_*` 镜像。
- 文件最大且视频轨有效。
- 修改时间晚于其他候选。

### 选择项目模式

1. 用户切换到 `选择项目`。
2. 用户选择某个剪映项目目录。
3. 工具扫描该项目本体和同名 `.cloud_cache_*` 镜像目录。
4. 工具展示全部候选缓存。
5. 用户选择目标缓存并点击 `生成草稿`。

这个模式不要求剪映正在运行。

### 选择 MP4 模式

1. 用户切换到 `选择 MP4`。
2. 用户选择任意本地 MP4 文件。
3. 工具验证该文件是否有可导入的视频轨。
4. 用户输入或接受默认草稿名。
5. 工具创建新草稿。

这个模式用于自动识别和项目扫描都失败时的兜底，也可作为通用“MP4 转剪映草稿”能力。

## 4. GUI 策划

MVP 使用单窗口，避免做成复杂管理后台。

### 信息架构

1. 顶部状态栏
   - 剪映状态：`未运行` / `运行中` / `仅托盘`
   - 草稿目录
   - 当前模式
   - 最近检测时间

2. 模式切换
   - `自动识别`
   - `选择项目`
   - `选择 MP4`

3. 来源区
   - 自动模式：推荐项目、推荐原因、重新检测按钮。
   - 项目模式：项目目录选择器、扫描按钮。
   - MP4 模式：文件选择器、媒体信息。

4. 候选列表
   - 文件名
   - 来源：`项目目录` / `cloud_cache 镜像` / `手动文件`
   - 大小
   - 时长
   - 分辨率
   - 修改时间
   - 状态

5. 输出设置
   - 新草稿名称，默认：`提取_{来源名}_{yyyyMMdd_HHmmss}`
   - 草稿目录只读显示
   - 主按钮：`生成草稿`

6. 结果区
   - 新草稿名
   - 新草稿路径
   - 复制校验结果
   - 操作：`打开草稿目录`、`重新检测`、`我已确认可打开`

7. 日志区
   - 只展示产品级阶段。
   - 不直接把 Python 堆栈暴露给普通用户。

### 空状态文案

| 场景 | 文案 |
|---|---|
| 剪映未运行 | 未检测到剪映运行。仍可手动选择项目或 MP4。 |
| 未找到项目 | 没有找到最近活跃的剪映项目，请手动选择项目。 |
| 项目无缓存 | 这个项目还没有可用的复合片段缓存。请在剪映中完成预合成后重试。 |
| 缓存仍在写入 | 缓存文件仍在生成，请稍后重新检测。 |
| 伪 MP4 / 加密 blob | 文件不是可导入视频，已跳过。 |
| 复制完成 | 视频已复制到新草稿目录。 |
| 草稿创建完成 | 草稿已创建，请回到剪映首页查看。 |
| 用户确认 | 用户已确认剪映可见/可打开。 |

### 禁止文案

界面和文档不要出现以下承诺：

- `导出成功`
- `自动导出`
- `破解 VIP`
- `无损导出完成`
- `已打开剪映草稿`
- `已确认可播放`
- `自动识别当前编辑界面`
- `已完成剪映内导出`
- `一键控制剪映`
- `检测到的 MP4 一定可用`

## 5. 能力契约

### 状态定义

| 状态 | 含义 |
|---|---|
| `detected` | 已找到候选来源或候选视频。 |
| `validated` | 已确认视频轨、尺寸、时长满足导入条件。 |
| `copying` | 正在复制源视频到新草稿目录。 |
| `copied` | 已复制，源文件和目标文件大小一致。 |
| `draft_created` | 新草稿文件已写入。 |
| `user_verified_openable` | 用户手动确认剪映中可见/可打开。 |
| `failed` | 本次流程失败，需提供错误码和下一步建议。 |

只有用户点击确认后，状态才允许升级为 `user_verified_openable`。软件不能自行推断“可播放”。

### 输入

- 自动模式：草稿根目录、剪映进程状态、最近项目文件 mtime。
- 项目模式：用户选择的项目目录。
- MP4 模式：用户选择的 MP4 路径、可选来源名。

### 输出

- 新草稿目录。
- 新草稿名。
- 复制后媒体路径。
- 结构化结果 JSON。
- 诊断日志。

### 不变量

- 永远不写入原项目目录。
- 永远不写入 `.cloud_cache_*` 目录。
- 永远不删除原缓存。
- 草稿创建失败时必须清理本次半成品目录，或明确记录未清理原因。
- GUI 和 CLI 必须走同一个工作流服务，避免两套逻辑漂移。

## 6. 架构方案

下一阶段不要继续把业务规则堆进 `gui.py` 或 `__main__.py`。需要抽出统一服务层。

```text
自动识别当前活跃项目
手动指定项目目录
手动指定 MP4 文件
        ↓
SourceResolver
        ↓
CacheScanner / MediaValidator
        ↓
Workflow
        ↓
DraftCreationService
        ↓
CLI / GUI / future API
```

### 模块边界

| 模块 | 职责 |
|---|---|
| `models.py` | 统一 dataclass / enum / 错误码。 |
| `media_validator.py` | 视频轨验证、文件稳定性、复制校验、hash。 |
| `cache_extractor.py` | 只扫描 `Resources/combination`，不做来源决策。 |
| `project_detector.py` | 只推荐活跃项目，不直接决定最终 MP4。 |
| `source_resolver.py` | 解析 `auto` / `project` / `mp4` 三种来源。 |
| `workflow.py` | `scan_source()` 和 `create_draft_from_source()` 主流程。 |
| `draft_creator.py` | 给定已验证 MP4 创建新草稿，负责回滚。 |
| `gui.py` | 展示和用户交互，不写业务规则。 |
| `__main__.py` | CLI 参数解析和结构化输出。 |

### 现有模块调整

- `cache_extractor.inspect_video()` 迁移到 `media_validator.validate_media_file()`，返回可解释的状态，而不是只返回三元组。
- `project_detector.detect_active_project()` 保留为自动模式信号源，但不要复用于手动项目扫描。
- `draft_creator.create_extracted_draft()` 增加原子唯一命名、复制校验、失败回滚。
- `__main__.py` 从 `detect/list/extract` 逐步迁移到 `scan/create`。
- `gui.py` 从单一自动检测界面升级为三模式界面。

## 7. 数据模型草案

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class SourceMode(str, Enum):
    AUTO = "auto"
    PROJECT = "project"
    MP4 = "mp4"


class CacheOrigin(str, Enum):
    PROJECT = "project"
    CLOUD_CACHE = "cloud_cache"
    MANUAL_FILE = "manual_file"


class CandidateStatus(str, Enum):
    AVAILABLE = "available"
    WRITING = "writing"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MediaCandidate:
    path: Path
    origin: CacheOrigin
    source_project_name: str | None
    size_bytes: int
    modified_at: datetime
    width: int | None
    height: int | None
    duration_ms: float | None
    status: CandidateStatus
    score: int = 0
    rejection_reason: str | None = None


@dataclass(frozen=True)
class CreateDraftRequest:
    mode: SourceMode
    project_path: Path | None = None
    mp4_path: Path | None = None
    source_name: str | None = None
    selected_media_path: Path | None = None
    fps: int = 30
    require_confirmed_candidate: bool = True


@dataclass(frozen=True)
class CreatedDraft:
    name: str
    draft_path: Path
    media_path: Path
    source_media_path: Path
    size_verified: bool
    sha256: str | None = None


@dataclass(frozen=True)
class CreateDraftResult:
    status: str
    mode: SourceMode
    selected_media: MediaCandidate | None
    created_draft: CreatedDraft | None
    warnings: list[str]
```

## 8. 扫描策略

### 自动模式

1. 检查剪映进程状态。
2. 扫描草稿根目录下非隐藏项目。
3. 用 `draft_content.json`、`draft_content.json.bak`、`draft.extra` 的 mtime 作为活跃度信号。
4. 扫描项目本体 `Resources/combination`。
5. 如果本体无有效视频，再扫描 `.cloud_cache_* / 项目名 / Resources / combination`。
6. 如果多个项目或镜像都有候选，按分数排序并显示推荐原因。
7. 不静默创建草稿，必须由用户确认候选。

### 手动项目模式

1. 不要求剪映运行。
2. 扫描用户选择的项目目录。
3. 同时查找草稿根目录下所有同名 `.cloud_cache_*` 镜像。
4. 展示所有候选。
5. 如果本体和镜像都有可用视频，不自动覆盖用户选择。

### 手动 MP4 模式

1. 不依赖剪映项目。
2. 验证用户选择的 MP4。
3. 如果通过验证，直接进入草稿创建流程。
4. 默认来源名来自文件名，也允许用户输入。

## 9. 校验与审计要求

### 媒体校验

媒体文件必须满足：

- 后缀是 `.mp4`。
- 不是 `.alpha.mp4`。
- 大小大于最小阈值。
- MediaInfo 能读出视频轨或图片轨。
- `width > 0`。
- `height > 0`。
- `duration_ms > 0`。
- 文件稳定：连续 2-3 次采样，size 和 mtime 不再变化。
- 复制后源文件和目标文件 size 一致。
- v0.2 增加 SHA-256 校验。

拒绝原因必须可解释：

- `empty_file`
- `alpha_sidecar`
- `not_mp4`
- `no_video_track`
- `invalid_duration`
- `still_writing`
- `read_failed`

### 草稿创建校验

草稿创建必须满足：

- 新草稿名唯一。
- 草稿目录通过原子 `mkdir` 或 UUID 后缀创建，避免同秒重名。
- 写入失败时清理本次创建的半成品目录。
- 创建后验证 `draft_content.json` 和 `draft_meta_info.json` 存在。
- 复制后目标 MP4 存在且大小一致。
- 不修改原项目和源缓存。

### 日志要求

每次运行记录：

- `run_id`
- 剪映版本
- 草稿根目录
- 来源模式
- 候选项目列表
- 候选 MP4 路径、大小、mtime、时长、分辨率
- 文件稳定性检测结果
- 复制前后 size/hash
- 新草稿名和路径
- 最终状态
- warnings 和错误码

## 10. CLI 设计

CLI 分为两类：扫描和创建。

```bash
python -m jianying_controller scan --auto --json
python -m jianying_controller scan --project "D:\...\项目名" --json
python -m jianying_controller scan --mp4 "D:\...\xxx.mp4" --source-name "xxx" --json

python -m jianying_controller create --auto --json
python -m jianying_controller create --project "D:\...\项目名" --media "D:\...\cache.mp4" --json
python -m jianying_controller create --mp4 "D:\...\xxx.mp4" --source-name "xxx" --json
```

成功输出：

```json
{
  "status": "draft_created",
  "mode": "project",
  "selected_media": {
    "path": "...",
    "origin": "cloud_cache",
    "size_bytes": 122000000,
    "width": 1920,
    "height": 1080,
    "duration_ms": 124000
  },
  "created_draft": {
    "name": "提取_xxx_20260528_210210",
    "draft_path": "...",
    "media_path": "...",
    "size_verified": true
  },
  "warnings": []
}
```

失败输出：

```json
{
  "status": "failed",
  "code": "no_valid_media",
  "message": "未找到可导入的视频缓存",
  "details": []
}
```

## 11. 测试矩阵

| 范围 | 用例 |
|---|---|
| 自动识别 | 剪映运行且最近项目有有效 cloud_cache。 |
| 自动识别 | 剪映未运行时返回可解释失败。 |
| 项目扫描 | 手动项目目录能扫描本体 combination。 |
| 项目扫描 | 本体无效但 cloud_cache 有效时命中镜像。 |
| MP4 模式 | 任意有效 MP4 能生成草稿。 |
| 媒体过滤 | `.alpha.mp4` 被跳过。 |
| 媒体过滤 | 0 字节文件被跳过。 |
| 媒体过滤 | 伪 MP4 / 加密 blob 被跳过。 |
| 文件稳定性 | 正在增长的文件不允许复制。 |
| 草稿创建 | 复制后 size 一致。 |
| 草稿创建 | `script.save()` 失败时清理半成品目录。 |
| 草稿创建 | 同秒重复生成不会重名。 |
| CLI | 成功时输出结构化 JSON。 |
| CLI | 失败时输出结构化 JSON 和错误码。 |
| GUI | 三模式可切换，按钮状态正确。 |
| 文案 | 完成后不出现“导出成功”。 |

建议新增测试文件：

- `tests/test_media_validator.py`
- `tests/test_source_resolver.py`
- `tests/test_workflow.py`
- `tests/test_cli_contract.py`
- `tests/test_draft_creator_recovery.py`

## 12. 两周实施路线

| 时间 | 里程碑 | 交付物 |
|---|---|---|
| Day 1 | 链路固化 | 保留当前已验证路径，补充真实样本记录。 |
| Day 2 | 模型层 | 新增 `models.py`，统一状态和数据结构。 |
| Day 3 | 校验层 | 新增 `media_validator.py`，实现视频轨、稳定性、复制校验。 |
| Day 4 | 来源层 | 新增 `source_resolver.py`，统一 auto/project/mp4。 |
| Day 5 | 工作流层 | 新增 `workflow.py`，CLI/GUI 统一调用。 |
| Day 6 | 草稿稳态 | `draft_creator.py` 增加回滚、唯一命名、结果验证。 |
| Day 7 | CLI v0.1 | `scan/create` 命令和 JSON 契约。 |
| Day 8-9 | GUI v0.1 | 三模式界面、候选列表、日志、打开目录。 |
| Day 10 | 异常保护 | 空缓存、坏 MP4、权限、磁盘不足、重名。 |
| Day 11 | 端到端验收 | 用真实 116.6MB 缓存生成草稿，用户确认剪映可见。 |
| Day 12 | 打包 | PyInstaller onedir、README、诊断按钮。 |
| Day 13 | 回归 | 多项目、多 cloud_cache、手动 MP4 回归。 |
| Day 14 | beta | v0.1 beta、验收清单、已知限制。 |

## 13. 验收标准

### 产品验收

- 自动模式能推荐当前项目，但需要用户确认候选。
- 手动项目模式在剪映未运行时也可扫描。
- 手动 MP4 模式可从任意有效 MP4 生成草稿。
- 空状态给出下一步建议。
- 完成后只说“草稿已创建”，不说“导出成功”。
- 用户确认按钮能把状态升级为 `user_verified_openable`。

### 技术验收

- `.alpha.mp4`、0 字节、伪 MP4、加密 blob 被跳过。
- 本体缓存无效时可命中 `.cloud_cache_*` 镜像。
- 文件仍在写入时不会复制。
- 复制后文件大小一致。
- 草稿 JSON 和 meta 文件存在。
- 创建失败会回滚半成品目录。
- CLI 成功和失败都返回结构化 JSON。
- GUI 和 CLI 调用同一个 workflow。

### 真实验收

- 使用项目 `5月28日 (1)-副本` 的 `.cloud_cache_*` 有效 MP4 可创建新草稿。
- 用户在剪映草稿箱能看到新草稿。
- 用户确认可打开、可播放后，状态记录为 `user_verified_openable`。

## 14. 发布策略

v0.1 先做 Windows portable 包：

```text
JianYingCacheExtractor/
  JianYingCacheExtractor.exe
  config.json
  README.md
  logs/
```

发布要求：

- PyInstaller `--onedir` 优先。
- 首次启动自动探测剪映路径和草稿目录。
- 提供 `复制诊断信息` 按钮。
- README 明确说明需要用户先在剪映里完成复合片段预合成。
- 内部 beta 先用 5-10 个真实项目验证，再考虑 stable。

## 15. 下一步优先级

1. 新增 `models.py` 和 `media_validator.py`。
2. 新增 `source_resolver.py`，统一自动项目、手动项目、手动 MP4。
3. 新增 `workflow.py`，让 CLI/GUI 共用业务流程。
4. 加固 `draft_creator.py`：文件稳定性、复制校验、失败回滚、唯一命名。
5. 重写 CLI 为 `scan/create`。
6. GUI 改成三模式，不再只有自动检测。
7. 补充测试矩阵并跑真实项目回归。

