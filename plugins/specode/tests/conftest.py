"""Shared pytest fixtures for specode lite tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def scripts_dir() -> Path:
    return SCRIPTS_DIR


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    monkeypatch.delenv("SPECODE_GUARD", raising=False)
    return tmp_path


@pytest.fixture
def run_script(scripts_dir: Path, fake_home: Path):
    def _run(script_name: str, *args: str, stdin: Optional[str] = None,
             extra_env: Optional[dict] = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = str(fake_home)
        env["USERPROFILE"] = str(fake_home)
        env.setdefault("XDG_CONFIG_HOME", str(fake_home / ".config"))
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        if extra_env:
            env.update(extra_env)
        cmd = [sys.executable, str(scripts_dir / script_name), *args]
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              input=stdin if stdin is not None else "",
                              env=env, timeout=30)
    return _run
