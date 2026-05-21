"""Tests for spec_vault.py — three-tier doc_root resolution + status/detect/set."""
from __future__ import annotations

import getpass
import json
import platform
from pathlib import Path

import pytest


def _parse_status(stdout: str) -> dict:
    """spec_vault.py status emits a single JSON object (plus trailing \\n)."""
    return json.loads(stdout)


def _expected_device_segment() -> str:
    """Mirror spec_vault._device_segment so tests can predict the suffix."""
    sys_map = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}
    os_name = sys_map.get(platform.system(), platform.system().lower())
    return f"{os_name}-{getpass.getuser()}"


def test_status_with_env_override(run_script, fake_home, doc_root):
    """When SPECODE_ROOT env is set (doc_root fixture sets it), source=env."""
    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0, cp.stderr
    out = _parse_status(cp.stdout)
    assert out["source"] == "env"
    assert out["doc_root"] == str(doc_root)
    assert out["exists"] is True
    assert out["env_SPECODE_ROOT"] == str(doc_root)


def test_status_with_config_only(run_script, fake_home, monkeypatch):
    """SPECODE_ROOT unset + config.obsidianRoot present → source=config + device 段追加。"""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    cfg_dir = fake_home / ".config" / "specode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    target = fake_home / "my-vault"
    target.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({"obsidianRoot": str(target)}), encoding="utf-8"
    )
    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0, cp.stderr
    out = _parse_status(cp.stdout)
    assert out["source"] == "config"
    # obsidianRoot 命中 → 追加 spec-in/<device>
    assert out["doc_root"] == str(target / "spec-in" / _expected_device_segment())


def test_status_with_root_override_no_device_suffix(run_script, fake_home, monkeypatch):
    """config.rootOverride 命中 → 用户给什么用什么，不追加 device 段。"""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    cfg_dir = fake_home / ".config" / "specode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    target = fake_home / "explicit-root"
    target.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({"rootOverride": str(target)}), encoding="utf-8"
    )
    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0, cp.stderr
    out = _parse_status(cp.stdout)
    assert out["source"] == "config"
    assert out["doc_root"] == str(target)  # 无 spec-in/<device> 追加


def test_root_override_takes_precedence_over_obsidian_root(
    run_script, fake_home, monkeypatch,
):
    """同时存在 rootOverride 与 obsidianRoot 时，rootOverride 胜出（显式 > 隐式）。"""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    cfg_dir = fake_home / ".config" / "specode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    obs = fake_home / "obs-vault"
    obs.mkdir()
    explicit = fake_home / "explicit"
    explicit.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({"obsidianRoot": str(obs), "rootOverride": str(explicit)}),
        encoding="utf-8",
    )
    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0, cp.stderr
    out = _parse_status(cp.stdout)
    assert out["doc_root"] == str(explicit)  # rootOverride 优先且不追加


def test_status_with_none_returns_exit_3(run_script, fake_home, monkeypatch):
    """All three tiers miss → exit 3 + hint."""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    # No config, no obsidian config (fake HOME has neither)
    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 3, cp.stderr
    out = _parse_status(cp.stdout)
    assert out["source"] == "none"
    assert out["doc_root"] is None
    assert out["exists"] is False
    assert "hint" in out
    assert "SPECODE_ROOT" in out["hint"]


def test_detect_returns_empty_list_when_no_obsidian(run_script, fake_home, monkeypatch):
    """detect on a fake home with no obsidian.json → vaults=[]."""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    cp = run_script("spec_vault.py", "detect")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert "vaults" in out
    assert out["vaults"] == []
    assert out["count"] == 0
    assert "configs_checked" in out
    # configs_checked should be a non-empty list of paths under the fake home
    assert all(str(fake_home) in p for p in out["configs_checked"])


def test_set_vault_writes_config_and_status_reflects_config(
    run_script, fake_home, monkeypatch
):
    """`set --vault <p>` 写 obsidianRoot；status 反映 config + device 段追加。"""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    target = fake_home / "my-vault"
    target.mkdir()
    cp_set = run_script("spec_vault.py", "set", "--vault", str(target))
    assert cp_set.returncode == 0, cp_set.stderr
    set_payload = json.loads(cp_set.stdout)
    assert set_payload["ok"] is True
    # cmd_set 输出 doc_root 用 resolve_doc_root 重算 → 含 device 段
    expected = target.resolve() / "spec-in" / _expected_device_segment()
    assert set_payload["doc_root"] == str(expected)
    # config 字段：obsidianRoot 写入；rootOverride 不应存在
    cfg_path = fake_home / ".config" / "specode" / "config.json"
    assert cfg_path.exists()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["obsidianRoot"] == str(target.resolve())
    assert "rootOverride" not in cfg
    # status 同样反映
    cp_status = run_script("spec_vault.py", "status")
    assert cp_status.returncode == 0
    out = _parse_status(cp_status.stdout)
    assert out["source"] == "config"
    assert out["doc_root"] == str(expected)


def test_set_root_writes_root_override_no_device_suffix(run_script, fake_home, monkeypatch):
    """`set --root <p>` 写 rootOverride（不是 obsidianRoot）；doc_root 不追加 device 段。"""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    target = fake_home / "via-root"
    target.mkdir()
    cp = run_script("spec_vault.py", "set", "--root", str(target))
    assert cp.returncode == 0, cp.stderr
    set_payload = json.loads(cp.stdout)
    # --root 不追加 device 段
    assert set_payload["doc_root"] == str(target.resolve())
    cfg = json.loads(
        (fake_home / ".config" / "specode" / "config.json").read_text(encoding="utf-8")
    )
    # 写入字段是 rootOverride 不是 obsidianRoot
    assert cfg["rootOverride"] == str(target.resolve())
    assert "obsidianRoot" not in cfg


def test_set_vault_then_root_replaces_field(run_script, fake_home, monkeypatch):
    """先 set --vault 再 set --root：obsidianRoot 字段被清除、只保留 rootOverride。"""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    v = fake_home / "v1"
    v.mkdir()
    r = fake_home / "v2"
    r.mkdir()
    run_script("spec_vault.py", "set", "--vault", str(v))
    run_script("spec_vault.py", "set", "--root", str(r))
    cfg = json.loads(
        (fake_home / ".config" / "specode" / "config.json").read_text(encoding="utf-8")
    )
    assert cfg["rootOverride"] == str(r.resolve())
    assert "obsidianRoot" not in cfg


def test_set_nonexistent_path_returns_exit_3(run_script, fake_home, monkeypatch):
    """Setting a path that does not exist must fail without writing config."""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    cp = run_script("spec_vault.py", "set", "--vault", str(fake_home / "ghost"))
    assert cp.returncode == 3
    assert "不存在" in cp.stderr or "exists" not in cp.stderr.lower()


def test_env_overrides_config(run_script, fake_home, monkeypatch):
    """When both env and config present, env wins."""
    cfg_dir = fake_home / ".config" / "specode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    config_target = fake_home / "config-vault"
    config_target.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({"obsidianRoot": str(config_target)}), encoding="utf-8"
    )
    env_target = fake_home / "env-vault"
    env_target.mkdir()
    monkeypatch.setenv("SPECODE_ROOT", str(env_target))
    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0
    out = _parse_status(cp.stdout)
    assert out["source"] == "env"
    assert out["doc_root"] == str(env_target)
