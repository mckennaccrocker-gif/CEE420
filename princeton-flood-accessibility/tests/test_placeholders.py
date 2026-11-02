"""The dashboard is no longer a placeholder. Importing it must not exit."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dashboard_imports_without_serving() -> None:
    module = _load("dashboard.py")
    assert callable(module.main)
    assert callable(module.build_context)
