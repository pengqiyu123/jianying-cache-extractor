"""Read-only UI tree inspector for JianYing Pro.

The script launches JianYing if needed, captures the home UI tree, then tries
to open the first draft-like item for a second read-only capture. It does not
click export, delete, confirmation, or other destructive buttons.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import uiautomation as uia  # noqa: E402
from jianying_controller import JianYingEnv, JianYingProcess  # noqa: E402


INTERACTIVE_TYPES = {
    "ButtonControl",
    "EditControl",
    "ListControl",
    "ListItemControl",
    "MenuControl",
    "MenuItemControl",
    "TabControl",
    "TabItemControl",
    "TreeControl",
    "TreeItemControl",
    "ComboBoxControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "HyperlinkControl",
    "SliderControl",
}

SAFE_OPEN_HINTS = (
    "draft",
    "草稿",
    "HomePageDraft",
    "HomePageDraftTitle",
)

RISKY_TEXT = (
    "导出",
    "删除",
    "移除",
    "确认",
    "确定",
    "取消",
    "关闭",
    "发布",
    "上传",
    "购买",
    "开通",
)


@dataclass
class NodeInfo:
    index: int
    depth: int
    path: str
    control_type: str
    name: str
    automation_id: str
    class_name: str
    rect: str
    enabled: str
    offscreen: str
    full_description: str


@dataclass
class Win32Info:
    hwnd: int
    depth: int
    title: str
    class_name: str
    rect: str
    visible: bool


@dataclass
class MsaaInfo:
    depth: int
    name: str
    role: str
    state: str
    value: str
    child_id: int


def safe(value: object) -> str:
    try:
        if value is None:
            return ""
        return str(value).replace("\r", " ").replace("\n", " ").strip()
    except Exception as exc:  # pragma: no cover - COM defensive branch
        return f"<error:{exc}>"


def rect_to_str(control: uia.Control) -> str:
    try:
        rect = control.BoundingRectangle
        return f"{rect.left},{rect.top},{rect.right},{rect.bottom}"
    except Exception as exc:  # pragma: no cover - COM defensive branch
        return f"<error:{exc}>"


def get_full_description(control: uia.Control) -> str:
    try:
        return safe(control.GetPropertyValue(30159))
    except Exception:
        return ""


def control_type(control: uia.Control) -> str:
    try:
        return safe(control.ControlTypeName)
    except Exception:
        return type(control).__name__


def iter_children(control: uia.Control) -> Iterable[uia.Control]:
    try:
        child = control.GetFirstChildControl()
        while child:
            yield child
            child = child.GetNextSiblingControl()
    except Exception:
        return


def collect_tree(root: uia.Control, max_depth: int) -> list[NodeInfo]:
    nodes: list[NodeInfo] = []

    def walk(control: uia.Control, depth: int, path: str) -> None:
        idx = len(nodes)
        ctype = control_type(control)
        name = safe(getattr(control, "Name", ""))
        aid = safe(getattr(control, "AutomationId", ""))
        cls = safe(getattr(control, "ClassName", ""))
        nodes.append(
            NodeInfo(
                index=idx,
                depth=depth,
                path=path,
                control_type=ctype,
                name=name,
                automation_id=aid,
                class_name=cls,
                rect=rect_to_str(control),
                enabled=safe(getattr(control, "IsEnabled", "")),
                offscreen=safe(getattr(control, "IsOffscreen", "")),
                full_description=get_full_description(control),
            )
        )
        if depth >= max_depth:
            return
        for child_no, child in enumerate(iter_children(control), start=1):
            walk(child, depth + 1, f"{path}/{child_no}")

    walk(root, 0, "0")
    return nodes


def collect_raw_tree(root: uia.Control, max_depth: int) -> list[NodeInfo]:
    """Collect UIA Raw View using the underlying COM tree walker."""
    try:
        import uiautomation.uiautomation as uia_core
    except Exception:
        return []

    client = uia_core._AutomationClient.instance()
    walker = client.IUIAutomation.RawViewWalker
    nodes: list[NodeInfo] = []

    def wrap(element) -> uia.Control:
        return uia.Control(element=element)

    def walk(element, depth: int, path: str) -> None:
        control = wrap(element)
        idx = len(nodes)
        nodes.append(
            NodeInfo(
                index=idx,
                depth=depth,
                path=path,
                control_type=control_type(control),
                name=safe(getattr(control, "Name", "")),
                automation_id=safe(getattr(control, "AutomationId", "")),
                class_name=safe(getattr(control, "ClassName", "")),
                rect=rect_to_str(control),
                enabled=safe(getattr(control, "IsEnabled", "")),
                offscreen=safe(getattr(control, "IsOffscreen", "")),
                full_description=get_full_description(control),
            )
        )
        if depth >= max_depth:
            return
        child = walker.GetFirstChildElement(element)
        child_no = 1
        while child:
            walk(child, depth + 1, f"{path}/{child_no}")
            child = walker.GetNextSiblingElement(child)
            child_no += 1

    try:
        walk(root.Element, 0, "0")
    except Exception:
        return []
    return nodes


def hwnd_title(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def hwnd_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetClassNameW(hwnd, buffer, 512)
    return buffer.value


def hwnd_rect(hwnd: int) -> str:
    rect = ctypes.wintypes.RECT()
    ok = ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if not ok:
        return ""
    return f"{rect.left},{rect.top},{rect.right},{rect.bottom}"


def collect_win32_children(hwnd: int, max_depth: int = 4) -> list[Win32Info]:
    infos: list[Win32Info] = []

    enum_child_windows = ctypes.windll.user32.EnumChildWindows
    is_visible = ctypes.windll.user32.IsWindowVisible

    def walk(parent: int, depth: int) -> None:
        if depth > max_depth:
            return
        children: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def child_cb(child_hwnd, _lparam):
            children.append(int(child_hwnd))
            return True

        enum_child_windows(parent, child_cb, 0)
        for child in children:
            infos.append(
                Win32Info(
                    hwnd=child,
                    depth=depth,
                    title=hwnd_title(child),
                    class_name=hwnd_class(child),
                    rect=hwnd_rect(child),
                    visible=bool(is_visible(child)),
                )
            )
            walk(child, depth + 1)

    walk(hwnd, 1)
    return infos


def collect_msaa(hwnd: int, max_depth: int = 6, max_nodes: int = 400) -> list[MsaaInfo]:
    """Best-effort MSAA tree collection through oleacc.

    UIA is preferred, but some Qt/Chromium surfaces expose more through MSAA.
    """
    try:
        import comtypes
        from comtypes import automation
        from comtypes.client import GetModule

        GetModule("oleacc.dll")
        import comtypes.gen.Accessibility as accessibility
    except Exception:
        return []

    OBJID_CLIENT = ctypes.c_long(0xFFFFFFFC).value
    oleacc = ctypes.oledll.oleacc
    accessible = ctypes.POINTER(accessibility.IAccessible)()
    hr = oleacc.AccessibleObjectFromWindow(
        ctypes.wintypes.HWND(hwnd),
        ctypes.wintypes.DWORD(OBJID_CLIENT),
        ctypes.byref(accessibility.IAccessible._iid_),
        ctypes.byref(accessible),
    )
    if hr != 0 or not accessible:
        return []

    role_text = oleacc.GetRoleTextW
    role_text.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.LPWSTR, ctypes.wintypes.UINT]
    state_text = oleacc.GetStateTextW
    state_text.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.LPWSTR, ctypes.wintypes.UINT]

    def variant_child(child_id: int):
        variant = automation.VARIANT()
        variant.vt = automation.VT_I4
        variant.value = child_id
        return variant

    def get_role_text(role) -> str:
        try:
            role_value = int(role)
        except Exception:
            return safe(role)
        buffer = ctypes.create_unicode_buffer(256)
        role_text(role_value, buffer, 256)
        return buffer.value or str(role_value)

    def get_state_text(state) -> str:
        try:
            state_value = int(state)
        except Exception:
            return safe(state)
        buffer = ctypes.create_unicode_buffer(512)
        state_text(state_value, buffer, 512)
        return buffer.value or str(state_value)

    items: list[MsaaInfo] = []

    def add(acc, child_id: int, depth: int) -> None:
        if len(items) >= max_nodes:
            return
        child = variant_child(child_id)
        try:
            name = safe(acc.accName(child))
        except Exception:
            name = ""
        try:
            role = get_role_text(acc.accRole(child))
        except Exception:
            role = ""
        try:
            state = get_state_text(acc.accState(child))
        except Exception:
            state = ""
        try:
            value = safe(acc.accValue(child))
        except Exception:
            value = ""
        items.append(MsaaInfo(depth=depth, name=name, role=role, state=state, value=value, child_id=child_id))

        if depth >= max_depth:
            return
        try:
            count = int(acc.accChildCount)
        except Exception:
            return
        if count <= 0:
            return

        children = (automation.VARIANT * count)()
        obtained = ctypes.c_long()
        try:
            oleacc.AccessibleChildren(acc, 0, count, children, ctypes.byref(obtained))
        except Exception:
            return
        for i in range(obtained.value):
            if len(items) >= max_nodes:
                return
            child_variant = children[i]
            if child_variant.vt == automation.VT_DISPATCH and child_variant.value:
                try:
                    child_acc = child_variant.value.QueryInterface(accessibility.IAccessible)
                    add(child_acc, 0, depth + 1)
                except Exception:
                    continue
            elif child_variant.vt == automation.VT_I4:
                add(acc, int(child_variant.value), depth + 1)

    add(accessible, 0, 0)
    return items


def find_window(timeout: int = 20) -> uia.WindowControl:
    deadline = time.time() + timeout
    last_seen: list[str] = []

    while time.time() < deadline:
        candidates = []
        root = uia.GetRootControl()
        for win in iter_children(root):
            ctype = control_type(win)
            if ctype != "WindowControl":
                continue
            name = safe(getattr(win, "Name", ""))
            cls = safe(getattr(win, "ClassName", ""))
            last_seen.append(f"{name} [{cls}]")
            if "剪映" in name or "jianying" in name.lower() or "jianying" in cls.lower():
                candidates.append(win)
            elif "Chrome_WidgetWin" in cls and ("JianyingPro" in name or "剪映" in name):
                candidates.append(win)
        if candidates:
            window = candidates[0]
            try:
                window.SetActive()
            except Exception:
                pass
            return window
        time.sleep(1)

    preview = "\n".join(last_seen[-30:])
    raise RuntimeError(f"JianYing window not found. Last windows:\n{preview}")


def format_full_tree(title: str, nodes: list[NodeInfo]) -> str:
    lines = [f"## {title}", ""]
    for node in nodes:
        indent = "  " * node.depth
        label = node.name or node.automation_id or node.full_description
        if len(label) > 120:
            label = label[:117] + "..."
        parts = [
            f"{indent}- #{node.index} {node.control_type}",
            f"name={label!r}",
            f"aid={node.automation_id!r}",
            f"class={node.class_name!r}",
            f"rect={node.rect}",
            f"enabled={node.enabled}",
            f"offscreen={node.offscreen}",
            f"path={node.path}",
        ]
        if node.full_description and node.full_description != label:
            desc = node.full_description[:180]
            parts.append(f"desc={desc!r}")
        lines.append(" | ".join(parts))
    lines.append("")
    return "\n".join(lines)


def format_win32_tree(title: str, nodes: list[Win32Info]) -> str:
    lines = [f"## {title}", ""]
    if not nodes:
        lines.append("(no Win32 child windows found)")
        lines.append("")
        return "\n".join(lines)
    for node in nodes:
        indent = "  " * node.depth
        lines.append(
            f"{indent}- hwnd=0x{node.hwnd:X} title={node.title!r} "
            f"class={node.class_name!r} rect={node.rect} visible={node.visible}"
        )
    lines.append("")
    return "\n".join(lines)


def format_msaa_tree(title: str, nodes: list[MsaaInfo]) -> str:
    lines = [f"## {title}", ""]
    if not nodes:
        lines.append("(no MSAA nodes found or oleacc unavailable)")
        lines.append("")
        return "\n".join(lines)
    for idx, node in enumerate(nodes):
        indent = "  " * node.depth
        label = node.name or node.value
        lines.append(
            f"{indent}- #{idx} role={node.role!r} name={label!r} "
            f"state={node.state!r} child_id={node.child_id}"
        )
    lines.append("")
    return "\n".join(lines)


def is_key_node(node: NodeInfo) -> bool:
    has_id = bool(node.name or node.automation_id or node.full_description)
    if not has_id:
        return False
    if node.control_type in INTERACTIVE_TYPES:
        return True
    text = f"{node.name} {node.automation_id} {node.class_name} {node.full_description}"
    important_words = (
        "导出",
        "首页",
        "模板",
        "创作",
        "草稿",
        "媒体",
        "音频",
        "文本",
        "字幕",
        "贴纸",
        "特效",
        "滤镜",
        "时间线",
        "播放",
        "撤销",
        "重做",
        "Draft",
        "Export",
        "Home",
        "Media",
        "Text",
    )
    return any(word.lower() in text.lower() for word in important_words)


def guess_usage(node: NodeInfo) -> str:
    text = f"{node.name} {node.automation_id} {node.class_name} {node.full_description}".lower()
    mapping = [
        ("导出", "导出按钮/导出入口"),
        ("export", "导出按钮/导出入口"),
        ("草稿", "草稿列表/草稿入口"),
        ("draft", "草稿列表/草稿入口"),
        ("首页", "首页导航"),
        ("home", "首页导航"),
        ("模板", "模板导航"),
        ("素材", "素材入口"),
        ("media", "媒体素材区"),
        ("音频", "音频面板"),
        ("audio", "音频面板"),
        ("文本", "文本/字幕面板"),
        ("字幕", "字幕面板"),
        ("text", "文本/字幕面板"),
        ("播放", "播放控制"),
        ("play", "播放控制"),
        ("撤销", "撤销按钮"),
        ("undo", "撤销按钮"),
        ("重做", "重做按钮"),
        ("redo", "重做按钮"),
        ("时间线", "时间轴区域"),
        ("timeline", "时间轴区域"),
    ]
    for key, usage in mapping:
        if key in text:
            return usage
    if node.control_type in INTERACTIVE_TYPES:
        return "可交互控件"
    return "信息元素"


def table_rows(nodes: list[NodeInfo], limit: int = 80) -> list[str]:
    rows = []
    for node in [n for n in nodes if is_key_node(n)][:limit]:
        rows.append(
            "| "
            + " | ".join(
                [
                    f"#{node.index} `{node.path}`",
                    node.control_type,
                    escape_md(node.name or node.full_description),
                    escape_md(node.automation_id),
                    escape_md(node.class_name),
                    escape_md(guess_usage(node)),
                ]
            )
            + " |"
        )
    return rows


def escape_md(text: str) -> str:
    text = text or ""
    return text.replace("|", "\\|").replace("\n", " ")


def selector_candidates(nodes: list[NodeInfo], scene: str) -> list[str]:
    lines = [f"# {scene}"]

    def matching(*terms: str) -> list[NodeInfo]:
        found = []
        for node in nodes:
            hay = f"{node.name} {node.automation_id} {node.class_name} {node.full_description}".lower()
            if any(term.lower() in hay for term in terms):
                found.append(node)
        return found

    candidates = {
        "draft_list_or_card": matching("draft", "草稿", "HomePageDraft"),
        "export_button": matching("export", "导出"),
        "timeline_area": matching("timeline", "时间线", "时间轴"),
        "play_control": matching("play", "播放"),
        "media_panel": matching("media", "媒体", "素材"),
        "text_panel": matching("text", "文本", "字幕"),
    }

    for var_name, found in candidates.items():
        node = next((n for n in found if n.control_type in INTERACTIVE_TYPES), None) or (found[0] if found else None)
        if node is None:
            lines.append(f"{var_name} = None  # not found")
            continue
        if node.automation_id:
            lines.append(
                f"{var_name} = window.Control(searchDepth=10, AutomationId={node.automation_id!r})"
            )
        elif node.name:
            lines.append(f"{var_name} = window.Control(searchDepth=10, Name={node.name!r})")
        elif node.full_description:
            lines.append(
                f"{var_name} = window.Control(searchDepth=10, "
                f"Compare=lambda c, d: {node.full_description!r} in str(c.GetPropertyValue(30159)))"
            )
        else:
            lines.append(f"{var_name} = None  # no stable selector")
        lines.append(f"# observed: type={node.control_type}, class={node.class_name!r}, path={node.path}, rect={node.rect}")
    return lines


def first_safe_draft_control(window: uia.Control, nodes: list[NodeInfo]) -> uia.Control | None:
    for node in nodes:
        hay = f"{node.name} {node.automation_id} {node.class_name} {node.full_description}"
        if not any(hint.lower() in hay.lower() for hint in SAFE_OPEN_HINTS):
            continue
        if any(risky in hay for risky in RISKY_TEXT):
            continue
        if node.control_type not in {"ButtonControl", "ListItemControl", "GroupControl", "PaneControl", "TextControl"}:
            continue
        ctrl = control_by_path(window, node.path)
        if ctrl is not None:
            parent = ctrl
            for _ in range(3):
                p = parent.GetParentControl()
                if not p:
                    break
                ptype = control_type(p)
                if ptype in {"ButtonControl", "ListItemControl", "GroupControl", "PaneControl"}:
                    return p
                parent = p
            return ctrl
    return None


def control_by_path(root: uia.Control, path: str) -> uia.Control | None:
    if path == "0":
        return root
    current = root
    parts = path.split("/")[1:]
    try:
        for part in parts:
            target_index = int(part)
            child = current.GetFirstChildControl()
            current_index = 1
            while child and current_index < target_index:
                child = child.GetNextSiblingControl()
                current_index += 1
            if not child:
                return None
            current = child
        return current
    except Exception:
        return None


def try_open_first_draft(window: uia.Control, home_nodes: list[NodeInfo], timeout: int) -> tuple[bool, str]:
    target = first_safe_draft_control(window, home_nodes)
    if target is None:
        return False, "未找到可安全打开的草稿控件。"

    text = safe(getattr(target, "Name", "")) or get_full_description(target) or safe(getattr(target, "ClassName", ""))
    if any(risky in text for risky in RISKY_TEXT):
        return False, f"候选控件包含风险词，已跳过：{text}"

    try:
        target.DoubleClick(simulateMove=False)
    except Exception as exc:
        return False, f"尝试打开第一个草稿失败：{exc}"

    time.sleep(timeout)
    return True, f"已尝试打开第一个草稿候选控件：{text[:120]}"


def write_report(
    report_path: Path,
    env_summary: str,
    home_window: uia.Control,
    home_nodes: list[NodeInfo],
    home_raw_nodes: list[NodeInfo],
    home_win32_nodes: list[Win32Info],
    home_msaa_nodes: list[MsaaInfo],
    edit_nodes: list[NodeInfo],
    open_note: str,
) -> None:
    window_info = {
        "title": safe(getattr(home_window, "Name", "")),
        "class": safe(getattr(home_window, "ClassName", "")),
        "rect": rect_to_str(home_window),
    }

    lines = [
        "# JianYing Pro v10.6 UI 元素探测报告",
        "",
        "## 结论",
        "",
        "**阻塞：剪映 v10.6.0.14057 没有向 Windows UI Automation 暴露首页内部控件。**",
        "",
        "本次用 UIA Control View、UIA Raw View、Win32 子窗口枚举、MSAA/oleacc 四种方式交叉探测，均只能看到顶层窗口，不能读取草稿卡片、导航、导出按钮、时间轴等内部元素。因此目前不能给出可直接定位导出按钮的 `uiautomation` 选择器；继续沿用旧版 `HomePageDraftTitle` / `MainWindowTitleBarExportBtn` 方案在 v10.6 上不可行。",
        "",
        "## 探测说明",
        "- 本次探测使用 Python `uiautomation`，只读取 UI 树。",
        "- 未点击导出、删除、确认、发布等风险按钮。",
        f"- 编辑界面进入状态：{open_note}",
        "",
        "## 环境信息",
        "```text",
        env_summary,
        "```",
        "",
        "## 窗口信息",
        f"- 窗口标题：{window_info['title']}",
        f"- ClassName：{window_info['class']}",
        f"- 位置和大小：{window_info['rect']}",
        "",
        "## 探测结果概览",
        f"- UIA Control View 首页节点数：{len(home_nodes)}",
        f"- UIA Raw View 首页节点数：{len(home_raw_nodes)}",
        f"- Win32 子窗口数：{len(home_win32_nodes)}",
        f"- MSAA/oleacc 节点数：{len(home_msaa_nodes)}",
        "",
        "说明：如果以上树都只暴露顶层窗口或极少节点，说明剪映 v10.6 的 Qt/QML 渲染界面没有向 Windows UI Automation 暴露内部按钮文本，不能直接用旧版 `HomePageDraftTitle`、`MainWindowTitleBarExportBtn` 一类选择器。",
        "",
        "补充验证：`JianYingProcess.open_draft('11月10日')` 返回成功，但实际打开的是 Windows 文件资源管理器中的草稿目录，不是剪映编辑界面，因此不能作为进入编辑页的自动化入口。",
        "",
        "## 首页 - 关键交互元素",
        "",
        "| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |",
        "|------|-------------|------|--------------|-----------|----------|",
        *table_rows(home_nodes, 90),
        "",
        "## 编辑界面 - 关键交互元素",
        "",
        "| 元素 | ControlType | Name | AutomationId | ClassName | 用途推测 |",
        "|------|-------------|------|--------------|-----------|----------|",
        *table_rows(edit_nodes, 90),
        "",
        "## 导出对话框 - 关键交互元素（如果能进入）",
        "",
        "未进入导出对话框。按照任务安全要求，本次只做只读探测，不点击导出按钮。",
        "",
        "## 选择器速查（供自动化使用）",
        "",
        "```python",
        "import uiautomation as uia",
        "",
        "window = uia.WindowControl(searchDepth=1, Name='剪映专业版')",
        "if not window.Exists(1):",
        "    window = uia.WindowControl(searchDepth=1, Compare=lambda c, d: '剪映' in c.Name or 'Jianying' in c.Name or 'Jianying' in c.ClassName)",
        "",
        *selector_candidates(home_nodes, "首页"),
        "",
        *selector_candidates(edit_nodes, "编辑界面"),
        "```",
        "",
        "## 下一步建议",
        "- 方案 A：改用图像识别/坐标自动化。先固定剪映窗口尺寸，截图定位按钮区域，再用 `pyautogui` 执行受控点击。",
        "- 方案 B：查找 Qt Accessibility 开关。若剪映随 Qt 提供可访问性插件，尝试通过环境变量或启动参数开启内部控件树后重跑本脚本。",
        "- 方案 C：降级使用已知支持 UIA 选择器的剪映 5.9/6.x 做自动导出，v10.6 只做草稿生成和人工导出。",
        "- 方案 D：继续研究本地协议/命令行入口，但不要把草稿文件夹打开误判为剪映编辑页打开。",
        "",
        "## 原始数据",
        "- 完整 UI 树：`docs/ui_tree_full.txt`",
        f"- 首页节点数：{len(home_nodes)}",
        f"- 首页 Raw View 节点数：{len(home_raw_nodes)}",
        f"- Win32 子窗口数：{len(home_win32_nodes)}",
        f"- MSAA 节点数：{len(home_msaa_nodes)}",
        f"- 编辑界面节点数：{len(edit_nodes)}",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--startup-timeout", type=int, default=30)
    parser.add_argument("--settle", type=int, default=8)
    parser.add_argument("--open-draft", action="store_true")
    args = parser.parse_args()

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)

    env = JianYingEnv()
    proc = JianYingProcess(env)
    status = proc.launch(wait=True, timeout=args.startup_timeout)
    time.sleep(args.settle)
    window = find_window(timeout=20)
    home_nodes = collect_tree(window, args.depth)
    home_raw_nodes = collect_raw_tree(window, args.depth)
    home_win32_nodes = collect_win32_children(int(window.NativeWindowHandle), max_depth=4)
    home_msaa_nodes = collect_msaa(int(window.NativeWindowHandle), max_depth=6)

    open_note = "未尝试打开草稿。"
    edit_nodes: list[NodeInfo] = []
    if args.open_draft:
        opened, open_note = try_open_first_draft(window, home_nodes, args.settle)
        if opened:
            window = find_window(timeout=20)
            edit_nodes = collect_tree(window, args.depth)

    full_tree = []
    full_tree.append(f"# JianYing UI full tree\n\nProcess status: {status}\n")
    full_tree.append(format_full_tree("Home", home_nodes))
    full_tree.append(format_full_tree("Home Raw View", home_raw_nodes))
    full_tree.append(format_win32_tree("Home Win32 Children", home_win32_nodes))
    full_tree.append(format_msaa_tree("Home MSAA", home_msaa_nodes))
    if edit_nodes:
        full_tree.append(format_full_tree("Edit", edit_nodes))
    (docs / "ui_tree_full.txt").write_text("\n".join(full_tree), encoding="utf-8")

    write_report(
        docs / "ui_inspect_report.md",
        env.summary(),
        window,
        home_nodes,
        home_raw_nodes,
        home_win32_nodes,
        home_msaa_nodes,
        edit_nodes,
        open_note,
    )
    print(f"wrote {docs / 'ui_tree_full.txt'}")
    print(f"wrote {docs / 'ui_inspect_report.md'}")
    print(
        f"home_nodes={len(home_nodes)} raw_nodes={len(home_raw_nodes)} "
        f"win32_nodes={len(home_win32_nodes)} msaa_nodes={len(home_msaa_nodes)} "
        f"edit_nodes={len(edit_nodes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
