"""Placeholders must fail clearly instead of pretending to model floods."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "script",
    ["dashboard.py"],
)
def test_later_stage_script_errors(script: str) -> None:
    module = _load(script)
    with pytest.raises(SystemExit, match="not implemented"):
        module.main()
