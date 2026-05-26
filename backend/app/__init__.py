"""TCAlpha backend application package."""
from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
try:
    with _PYPROJECT.open("rb") as f:
        __version__: str = tomllib.load(f)["project"]["version"]
except (FileNotFoundError, KeyError):
    __version__ = "unknown"
