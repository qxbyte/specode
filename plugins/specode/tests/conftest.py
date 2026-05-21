"""Shared pytest fixtures for specode plugin tests (v0.6.0).

Bedrock rules:
  * Tests MUST be hermetic: never read or write the real $HOME/.specode.
  * Always redirect HOME / XDG_CONFIG_HOME / SPECODE_ROOT to tmp_path-based dirs.
  * Scripts are invoked as CLIs via subprocess (NOT imported as modules).
  * Each test uses a freshly-minted UUID session id to avoid cross-test pollution.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
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
    """Redirect $HOME to tmp_path so Path.home() resolves to an isolated dir.

    Also drop any inherited SPECODE_ROOT / XDG_CONFIG_HOME so child processes
    do not accidentally see user state. Tests that need those vars must set
    them explicitly via monkeypatch.setenv.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    # USERPROFILE for hypothetical Windows runners
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Pin XDG_CONFIG_HOME under fake home so spec_vault's config never
    # escapes to the real user's ~/.config.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    # APPDATA / LOCALAPPDATA are read by spec_vault.detect to find Obsidian
    # on Windows; pin them inside fake_home so a real Obsidian install on
    # the test machine cannot leak into the assertions.
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    monkeypatch.delenv("SPECODE_GUARD", raising=False)
    return tmp_path


@pytest.fixture
def specode_home(fake_home: Path) -> Path:
    """The simulated ~/.specode/ directory (parent of sessions/)."""
    return fake_home / ".specode"


@pytest.fixture
def doc_root(tmp_path: Path, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The simulated specode root (also written to SPECODE_ROOT env var).

    Uses a sub-dir of tmp_path that is sibling to fake_home so the two
    namespaces are well separated.
    """
    root = tmp_path / "vault" / "spec-in" / "test"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SPECODE_ROOT", str(root))
    return root


@pytest.fixture
def make_session_id():
    """Factory returning a fresh UUID string per call."""
    def _make() -> str:
        return str(uuid.uuid4())
    return _make


@pytest.fixture
def run_script(scripts_dir: Path, fake_home: Path):
    """Run a specode CLI script under the test-controlled environment.

    Usage:
        cp = run_script("spec_vault.py", "status")
        cp = run_script("spec_session.py", "on-user-prompt", stdin=json.dumps(...))
    """
    def _run(script_name: str, *args: str, stdin: Optional[str] = None,
             extra_env: Optional[dict] = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        # Make sure HOME redirection sticks (subprocesses inherit current env
        # which already has the monkeypatched HOME, but we re-assert for safety).
        env["HOME"] = str(fake_home)
        env["USERPROFILE"] = str(fake_home)
        env.setdefault("XDG_CONFIG_HOME", str(fake_home / ".config"))
        # Force Python UTF-8 mode in child: on Windows the default locale is
        # cp936/gbk which makes pathlib + stderr writes incompatible with the
        # utf-8 decoding we use here. Tests on macOS/Linux already default to
        # utf-8, so this is a no-op there.
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        if extra_env:
            env.update(extra_env)
        cmd = [sys.executable, str(scripts_dir / script_name), *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=stdin if stdin is not None else "",
            env=env,
            timeout=30,
        )
    return _run


# --------------------------------------------------------------------------
# helper: create a working spec dir + session file the way spec_init would
# --------------------------------------------------------------------------

@pytest.fixture
def init_spec(run_script, doc_root: Path, make_session_id):
    """Initialise a spec via spec_init.py and return (slug, session_id, spec_dir, payload).

    Useful for tests of spec_session that need a real spec to operate on.
    """
    def _init(slug: str = "demo-spec", requirement_name: str = "Demo Spec",
              source_text: str = "测试用源需求文本",
              session_id: Optional[str] = None):
        sid = session_id or make_session_id()
        cp = run_script(
            "spec_init.py",
            "--name", slug,
            "--requirement-name", requirement_name,
            "--source-text", source_text,
            "--session", sid,
        )
        assert cp.returncode == 0, f"spec_init failed: {cp.stderr}\n{cp.stdout}"
        payload = json.loads(cp.stdout)
        spec_dir = Path(payload["spec_dir"])
        return slug, sid, spec_dir, payload
    return _init
