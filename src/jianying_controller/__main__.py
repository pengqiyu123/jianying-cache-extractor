"""Command entry for JianYing cache extraction."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

from .cache_extractor import find_combination_mp4s
from .draft_creator import create_extracted_draft
from .env import JianYingEnv
from .gui import main as gui_main
from .models import CreateDraftRequest, SourceMode, WorkflowError
from .project_detector import detect_active_project
from .workflow import create_draft_from_source, scan_source


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))


def request_from_args(args: argparse.Namespace) -> CreateDraftRequest:
    selected_media_path = Path(args.media) if getattr(args, "media", None) else None
    if getattr(args, "auto", False):
        return CreateDraftRequest(
            mode=SourceMode.AUTO,
            selected_media_path=selected_media_path,
            source_name=getattr(args, "source_name", None),
        )
    if getattr(args, "project", None):
        return CreateDraftRequest(
            mode=SourceMode.PROJECT,
            project_path=Path(args.project),
            selected_media_path=selected_media_path,
            source_name=getattr(args, "source_name", None),
        )
    if getattr(args, "mp4", None):
        return CreateDraftRequest(
            mode=SourceMode.MP4,
            mp4_path=Path(args.mp4),
            source_name=getattr(args, "source_name", None),
        )
    raise WorkflowError("source_required", "请指定 --auto、--project 或 --mp4")


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        source = scan_source(request_from_args(args))
    except WorkflowError as exc:
        print_json(exc.to_dict())
        return 1
    payload = {
        "status": "detected",
        "mode": source.mode,
        "source_name": source.source_name,
        "project_path": source.project_path,
        "candidates": source.candidates,
        "warnings": source.warnings or [],
    }
    print_json(payload)
    return 0 if source.available_candidates else 1


def cmd_create(args: argparse.Namespace) -> int:
    try:
        result = create_draft_from_source(request_from_args(args))
    except WorkflowError as exc:
        print_json(exc.to_dict())
        return 1
    print_json(result)
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    env = JianYingEnv()
    project = detect_active_project(env.info.draft_dir)
    if project is None:
        print("No active project with combination MP4 cache found.")
        return 1
    payload = {
        "name": project.name,
        "path": str(project.path),
        "latest_mp4": str(project.latest_mp4) if project.latest_mp4 else None,
        "last_modified": project.last_modified.isoformat(),
        "cache_count": len(project.caches),
    }
    print_json(payload)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    project = Path(args.project)
    files = find_combination_mp4s(project)
    for item in files:
        print(f"{item.modified_at:%Y-%m-%d %H:%M:%S}\t{item.size_bytes}\t{item.path}")
    return 0 if files else 1


def cmd_extract(args: argparse.Namespace) -> int:
    env = JianYingEnv()
    mp4 = Path(args.mp4)
    source_name = args.source_name or mp4.parent.parent.parent.name
    created = create_extracted_draft(env.info.draft_dir, mp4, source_name)
    payload = {
        "name": created.name,
        "draft_path": str(created.draft_path),
        "media_path": str(created.media_path),
        "source_media_path": str(created.source_media_path),
    }
    print_json(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JianYing cache extractor")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="scan automatic, project, or MP4 source")
    scan_source_group = scan.add_mutually_exclusive_group(required=True)
    scan_source_group.add_argument("--auto", action="store_true", help="scan active project")
    scan_source_group.add_argument("--project", help="draft project path")
    scan_source_group.add_argument("--mp4", help="manual MP4 path")
    scan.add_argument("--source-name", help="source name for manual MP4")
    scan.add_argument("--json", action="store_true", help="output JSON")
    scan.set_defaults(func=cmd_scan)

    create = sub.add_parser("create", help="create a new draft from a source")
    create_source_group = create.add_mutually_exclusive_group(required=True)
    create_source_group.add_argument("--auto", action="store_true", help="use active project")
    create_source_group.add_argument("--project", help="draft project path")
    create_source_group.add_argument("--mp4", help="manual MP4 path")
    create.add_argument("--media", help="selected media path from scan results")
    create.add_argument("--source-name", help="source name")
    create.add_argument("--json", action="store_true", help="output JSON")
    create.set_defaults(func=cmd_create)

    detect = sub.add_parser("detect", help="detect the active project")
    detect.set_defaults(func=cmd_detect)

    list_cmd = sub.add_parser("list", help="list combination MP4 caches")
    list_cmd.add_argument("project", help="draft project path")
    list_cmd.set_defaults(func=cmd_list)

    extract = sub.add_parser("extract", help="create a new draft from a cache MP4")
    extract.add_argument("mp4", help="combination MP4 path")
    extract.add_argument("--source-name", help="source project name")
    extract.set_defaults(func=cmd_extract)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        gui_main()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
