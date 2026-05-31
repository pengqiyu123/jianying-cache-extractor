"""Command-line entrypoint for JianYing cache extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .auto_import import auto_import_file
from .compound_clip import run_compound_clip_sequence, run_uncompose_clip_sequence
from .gui import main as gui_main
from .models import CreateDraftRequest, SourceMode, WorkflowError
from .private_prepare import restart_jianying_for_import
from .workflow import create_draft_from_source, scan_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jianying_controller")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan")
    scan_group = scan.add_mutually_exclusive_group(required=True)
    scan_group.add_argument("--auto", action="store_true")
    scan_group.add_argument("--project")
    scan_group.add_argument("--mp4")
    scan.add_argument("--source-name")
    scan.add_argument("--json", action="store_true")

    create = subparsers.add_parser("create")
    create_group = create.add_mutually_exclusive_group(required=True)
    create_group.add_argument("--auto", action="store_true")
    create_group.add_argument("--project")
    create_group.add_argument("--mp4")
    create.add_argument("--media")
    create.add_argument("--source-name")
    create.add_argument("--draft-name")
    create.add_argument("--json", action="store_true")

    auto_import = subparsers.add_parser("auto-import")
    auto_import.add_argument("mp4")

    compound = subparsers.add_parser("compound-clip")
    compound.add_argument("--hotkey", default="shift+g")

    prepare = subparsers.add_parser("prepare-import")
    prepare.add_argument("mp4", nargs="?")

    subparsers.add_parser("uncompose-clip")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        gui_main()
        return 0
    try:
        payload = _dispatch(args)
    except WorkflowError as exc:
        _print_json({"status": "failed", "code": exc.code, "message": exc.message})
        return 1
    except Exception as exc:
        _print_json({"status": "failed", "code": "unexpected_error", "message": str(exc)})
        return 1
    _print_json(payload)
    return 0


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "scan":
        mode, kwargs = _source_args(args)
        source = scan_source(mode, source_name=getattr(args, "source_name", None), **kwargs)
        return {
            "status": "detected",
            "sourceName": source.source_name,
            "mode": source.mode.value,
            "candidates": [str(candidate.path) for candidate in source.candidates],
        }
    if args.command == "create":
        mode, kwargs = _source_args(args)
        selected_media_path = Path(args.media) if getattr(args, "media", None) else None
        result = create_draft_from_source(
            CreateDraftRequest(
                mode=mode,
                draft_name=args.draft_name,
                selected_media_path=selected_media_path,
                source_name=getattr(args, "source_name", None),
                **kwargs,
            )
        )
        return {
            "status": result.status,
            "mode": result.mode.value if result.mode else None,
            "draft": str(result.created_draft.draft_path) if result.created_draft else None,
        }
    if args.command == "auto-import":
        result = auto_import_file(args.mp4)
        return {"status": result.status, "error": result.error_detail}
    if args.command == "compound-clip":
        result = run_compound_clip_sequence(args.hotkey)
        return {"status": result.status, "warnings": result.warnings}
    if args.command == "prepare-import":
        result = restart_jianying_for_import()
        return {"status": result.status, "warnings": result.warnings}
    if args.command == "uncompose-clip":
        result = run_uncompose_clip_sequence()
        return {"status": result.status, "warnings": result.warnings}
    raise WorkflowError("unknown_command", f"未知命令: {args.command}")


def _source_args(args: argparse.Namespace) -> tuple[SourceMode, dict[str, Path]]:
    if getattr(args, "auto", False):
        return SourceMode.AUTO, {}
    if getattr(args, "project", None):
        return SourceMode.PROJECT, {"project_path": Path(args.project)}
    return SourceMode.MP4, {"mp4_path": Path(args.mp4)}


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
