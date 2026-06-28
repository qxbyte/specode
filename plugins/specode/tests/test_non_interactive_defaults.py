"""Regression tests for v0.9 M1/M9 — autonomous-mode defaults (3.4.0).

试跑结论：AskUserQuestion 在 autonomous mode 完全不可用，specode SKILL
的多处 user gate（specsRoot 设置 / project_root 确认 / 执行方式 selector /
distill 末尾 prompt）整条链路断。

修法：~/.config/specode/defaults.json + env var override + 5 个 schema 化
defaults key（interactive / project_root_default / execution_mode_default /
auto_distill / specs_root_default）。SKILL.md 改约：每个 AskUserQuestion
调用前 read-defaults，interactive=false + key 有值时直接用 default 不阻塞。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "scripts"
RR = REPO_ROOT / "resolve_root.py"


def _run(*args, env_extra: dict | None = None, fake_home: Path | None = None,
         xdg_home: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(RR), *args]
    env = os.environ.copy()
    # Strip any inherited SPECODE_* vars that would pollute the test.
    for k in list(env):
        if k.startswith("SPECODE_"):
            del env[k]
    if fake_home:
        env["HOME"] = str(fake_home)
    if xdg_home:
        env["XDG_CONFIG_HOME"] = str(xdg_home)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


# ---------- read-defaults ----------

def test_read_defaults_returns_schema_default_when_nothing_set(tmp_path: Path) -> None:
    """No env, no file → schema defaults returned."""
    r = _run("read-defaults", "--key", "interactive",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "true"


def test_read_defaults_json_key_metadata_includes_source(tmp_path: Path) -> None:
    """--json on single key returns {key, value, source} so callers can
    branch on whether value came from env / file / default."""
    r = _run("read-defaults", "--key", "interactive", "--json",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data == {"key": "interactive", "value": True, "source": "default"}


def test_read_defaults_all_keys_returns_full_map(tmp_path: Path) -> None:
    """No --key returns the entire schema dump (5 keys)."""
    r = _run("read-defaults",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert set(data.keys()) == {
        "interactive", "project_root_default", "execution_mode_default",
        "auto_distill", "specs_root_default",
    }
    assert all(isinstance(v, dict) and "value" in v and "source" in v
               for v in data.values())


def test_read_defaults_env_overrides_file_overrides_default(tmp_path: Path) -> None:
    """Priority: env > file > schema default."""
    xdg = tmp_path / "xdg"
    # 1. file sets interactive=false
    r1 = _run("write-default", "--key", "interactive", "--value", "false",
              fake_home=tmp_path, xdg_home=xdg)
    assert r1.returncode == 0
    r2 = _run("read-defaults", "--key", "interactive", "--json",
              fake_home=tmp_path, xdg_home=xdg)
    assert json.loads(r2.stdout)["source"] == "file"
    assert json.loads(r2.stdout)["value"] is False

    # 2. env var overrides file
    r3 = _run("read-defaults", "--key", "interactive", "--json",
              env_extra={"SPECODE_INTERACTIVE": "true"},
              fake_home=tmp_path, xdg_home=xdg)
    assert json.loads(r3.stdout)["source"] == "env"
    assert json.loads(r3.stdout)["value"] is True


def test_read_defaults_unknown_key_returns_error(tmp_path: Path) -> None:
    r = _run("read-defaults", "--key", "nonexistent_key",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 1
    assert "unknown defaults key" in r.stderr


def test_read_defaults_invalid_env_silently_falls_through(tmp_path: Path) -> None:
    """Invalid env value (e.g. SPECODE_INTERACTIVE=garbage) silently falls
    back to file/default — env is advisory, not a contract."""
    r = _run("read-defaults", "--key", "interactive", "--json",
             env_extra={"SPECODE_INTERACTIVE": "garbage"},
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["source"] == "default"  # fell through
    assert data["value"] is True


# ---------- write-default ----------

def test_write_default_persists_to_file(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    r = _run("write-default", "--key", "auto_distill", "--value", "false",
             fake_home=tmp_path, xdg_home=xdg)
    assert r.returncode == 0
    file_path = xdg / "specode" / "defaults.json"
    assert file_path.is_file()
    data = json.loads(file_path.read_text())
    assert data == {"auto_distill": False}


def test_write_default_validates_execution_mode_whitelist(tmp_path: Path) -> None:
    """execution_mode_default must be one of the known modes."""
    r = _run("write-default", "--key", "execution_mode_default",
             "--value", "invalid-mode",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 1
    assert "execution_mode_default must be one of" in r.stderr


def test_write_default_valid_execution_mode_succeeds(tmp_path: Path) -> None:
    r = _run("write-default", "--key", "execution_mode_default",
             "--value", "task-swarm",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 0


def test_write_default_rejects_unknown_key(tmp_path: Path) -> None:
    r = _run("write-default", "--key", "garbage_key", "--value", "x",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 1
    assert "unknown defaults key" in r.stderr


def test_write_default_rejects_invalid_bool_value(tmp_path: Path) -> None:
    r = _run("write-default", "--key", "interactive", "--value", "maybe",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 1
    assert "bool expected" in r.stderr or "invalid value" in r.stderr


# ---------- reset-default ----------

def test_reset_default_removes_single_key(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run("write-default", "--key", "auto_distill", "--value", "false",
         fake_home=tmp_path, xdg_home=xdg)
    _run("write-default", "--key", "interactive", "--value", "false",
         fake_home=tmp_path, xdg_home=xdg)

    r = _run("reset-default", "--key", "auto_distill",
             fake_home=tmp_path, xdg_home=xdg)
    assert r.returncode == 0
    data = json.loads((xdg / "specode" / "defaults.json").read_text())
    assert "auto_distill" not in data
    assert data.get("interactive") is False  # other keys untouched


def test_reset_default_all_removes_file(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    _run("write-default", "--key", "interactive", "--value", "false",
         fake_home=tmp_path, xdg_home=xdg)
    file_path = xdg / "specode" / "defaults.json"
    assert file_path.exists()

    r = _run("reset-default", "--all",
             fake_home=tmp_path, xdg_home=xdg)
    assert r.returncode == 0
    assert not file_path.exists()


def test_reset_default_requires_key_or_all(tmp_path: Path) -> None:
    r = _run("reset-default",
             fake_home=tmp_path, xdg_home=tmp_path / "xdg")
    assert r.returncode == 1
    assert "--key" in r.stderr and "--all" in r.stderr


# ---------- env var mapping completeness ----------

def test_all_schema_keys_have_env_var_override(tmp_path: Path) -> None:
    """Every schema key must map to a SPECODE_* env var — pin the contract."""
    # Use a key->env_var matrix and verify each env override actually flips source.
    matrix = [
        ("interactive", "SPECODE_INTERACTIVE", "false", False),
        ("project_root_default", "SPECODE_PROJECT_ROOT", "/tmp/some-root", "/tmp/some-root"),
        ("execution_mode_default", "SPECODE_EXECUTION_MODE", "task-swarm", "task-swarm"),
        ("auto_distill", "SPECODE_AUTO_DISTILL", "false", False),
        ("specs_root_default", "SPECODE_SPECS_ROOT_DEFAULT", "/tmp/specs", "/tmp/specs"),
    ]
    for key, env_var, env_value, expected in matrix:
        r = _run("read-defaults", "--key", key, "--json",
                 env_extra={env_var: env_value},
                 fake_home=tmp_path, xdg_home=tmp_path / "xdg")
        assert r.returncode == 0, f"{key}: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["source"] == "env", (
            f"{key}: env var {env_var}={env_value} should override schema "
            f"default; got source={data['source']}"
        )
        assert data["value"] == expected, (
            f"{key}: env override should coerce to {expected!r}; got {data['value']!r}"
        )
