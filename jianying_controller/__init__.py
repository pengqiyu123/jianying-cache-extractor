"""Project-root import shim for the src-layout package."""

from pathlib import Path

_src_package = Path(__file__).resolve().parent.parent / "src" / "jianying_controller"
if _src_package.exists():
    __path__.append(str(_src_package))

from src.jianying_controller import *  # noqa: F401,F403
