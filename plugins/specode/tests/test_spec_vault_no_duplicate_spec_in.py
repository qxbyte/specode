"""Tests for resolve_doc_root + set --vault 双重 spec-in/<device> 去重防御（0.10.27+）。

历史现场：用户的 ~/.config/specode/config.json 含
  "obsidianRoot": "/Volumes/External HD/Obsidian/Notes/spec-in/macos-xueqiang"
resolve_doc_root 又追加一次 spec-in/<device>，最终路径变成
  .../spec-in/macos-xueqiang/spec-in/macos-xueqiang  ❌

0.10.27 加入：
  1. resolve_doc_root 在 source=config 时检测 obsidianRoot 尾段是否已是
     `spec-in/<device>`，已是则不再追加。
  2. set --vault 在用户传入路径以 `spec-in/<device>` 结尾时，规范化为 vault 根
     再持久化（stderr 给出提示）。
"""
from __future__ import annotations

import getpass
import json
import platform
from pathlib import Path


def _device() -> str:
    sys_map = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}
    os_name = sys_map.get(platform.system(), platform.system().lower())
    return f"{os_name}-{getpass.getuser()}"


def _write_config(fake_home: Path, payload: dict) -> Path:
    cfg_dir = fake_home / ".config" / "specode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    p = cfg_dir / "config.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_resolve_doc_root_skips_append_when_obsidian_root_ends_with_device(
    run_script, fake_home, tmp_path
):
    """obsidianRoot 已含 `spec-in/<device>` 尾段 → resolve_doc_root 不再追加。"""
    device = _device()
    vault_root = tmp_path / "vault"
    full_path = vault_root / "spec-in" / device
    full_path.mkdir(parents=True)
    _write_config(fake_home, {"obsidianRoot": str(full_path)})

    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    # 单层 spec-in/<device>，不是双重
    assert payload["doc_root"] == str(full_path), (
        f"应保持单层：{full_path}，实际：{payload['doc_root']}"
    )
    # 验证：路径中 spec-in 只出现一次
    assert payload["doc_root"].count("spec-in") == 1


def test_resolve_doc_root_still_appends_when_obsidian_root_is_vault_root(
    run_script, fake_home, tmp_path
):
    """正常路径仍然成立：obsidianRoot = vault 根时追加 spec-in/<device>。"""
    device = _device()
    vault_root = tmp_path / "vault-clean"
    vault_root.mkdir()
    _write_config(fake_home, {"obsidianRoot": str(vault_root)})

    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    expected = vault_root / "spec-in" / device
    assert payload["doc_root"] == str(expected)


def test_set_vault_strips_device_suffix_when_user_passes_full_path(
    run_script, fake_home, tmp_path
):
    """`set --vault` 传入路径以 `spec-in/<device>` 结尾 → 抹掉再写。"""
    device = _device()
    vault_root = tmp_path / "vault-pass-full"
    full_with_suffix = vault_root / "spec-in" / device
    full_with_suffix.mkdir(parents=True)

    cp = run_script("spec_vault.py", "set", "--vault", str(full_with_suffix))
    assert cp.returncode == 0, cp.stderr
    # stderr 应有规范化提示
    assert "规范化" in cp.stderr
    assert device in cp.stderr
    # config.json 写入的应是 vault 根（不含尾段）
    cfg_p = fake_home / ".config" / "specode" / "config.json"
    cfg = json.loads(cfg_p.read_text("utf-8"))
    assert cfg["obsidianRoot"] == str(vault_root), (
        f"应抹掉 spec-in/{device} 尾段，实际写入：{cfg['obsidianRoot']}"
    )
    # 后续 status 应返回单层 spec-in/<device>
    payload = json.loads(cp.stdout)
    assert payload["doc_root"] == str(vault_root / "spec-in" / device)


def test_set_vault_normal_path_no_warning(
    run_script, fake_home, tmp_path
):
    """`set --vault` 传 vault 根（无 spec-in 尾段）→ 不触发规范化提示，正常写。"""
    vault_root = tmp_path / "vault-normal"
    vault_root.mkdir()

    cp = run_script("spec_vault.py", "set", "--vault", str(vault_root))
    assert cp.returncode == 0, cp.stderr
    assert "规范化" not in cp.stderr
    cfg_p = fake_home / ".config" / "specode" / "config.json"
    cfg = json.loads(cfg_p.read_text("utf-8"))
    assert cfg["obsidianRoot"] == str(vault_root)


def test_legacy_double_path_in_config_self_heals_on_read(
    run_script, fake_home, tmp_path
):
    """模拟用户现场：config.json 含完整 spec-in/<device> 尾段 → status 输出单层。

    relies on resolve_doc_root 去重防御；不要求 set --vault 介入（用户从未触发它）。
    """
    device = _device()
    vault_root = tmp_path / "external-hd" / "obsidian"
    legacy_full = vault_root / "spec-in" / device
    legacy_full.mkdir(parents=True)
    _write_config(fake_home, {"obsidianRoot": str(legacy_full)})

    cp = run_script("spec_vault.py", "status")
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    # 单层
    assert payload["doc_root"].count("spec-in") == 1
    assert payload["doc_root"] == str(legacy_full)
