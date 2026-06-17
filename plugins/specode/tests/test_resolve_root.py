"""Hermetic tests for resolve_root.py (specode 1.0.0 lite)."""
from __future__ import annotations

import json
from pathlib import Path


def _config_path(fake_home: Path) -> Path:
    return fake_home / ".config" / "specode" / "config.json"


def test_get_root_unconfigured_exits_3(run_script, fake_home):
    cp = run_script("resolve_root.py", "get-root")
    assert cp.returncode == 3, cp.stderr
    assert "specsRoot" in (cp.stdout + cp.stderr) or "未配置" in (cp.stdout + cp.stderr)


def test_set_root_persists_to_config(run_script, fake_home, tmp_path):
    target = tmp_path / "my-specs"
    target.mkdir()
    cp = run_script("resolve_root.py", "set-root", "--root", str(target))
    assert cp.returncode == 0, cp.stderr
    cfg = json.loads(_config_path(fake_home).read_text(encoding="utf-8"))
    assert cfg["specsRoot"] == str(target)


def test_set_root_rejects_relative(run_script, fake_home):
    cp = run_script("resolve_root.py", "set-root", "--root", "relative/path")
    assert cp.returncode == 1, cp.stderr


def test_set_root_preserves_other_keys(run_script, fake_home, tmp_path):
    cfgp = _config_path(fake_home)
    cfgp.parent.mkdir(parents=True, exist_ok=True)
    cfgp.write_text(json.dumps({"someOther": "keep-me"}), encoding="utf-8")
    target = tmp_path / "specs2"
    target.mkdir()
    cp = run_script("resolve_root.py", "set-root", "--root", str(target))
    assert cp.returncode == 0, cp.stderr
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    assert cfg["someOther"] == "keep-me"
    assert cfg["specsRoot"] == str(target)


def test_get_root_reads_config(run_script, fake_home, tmp_path):
    target = tmp_path / "specs3"
    target.mkdir()
    run_script("resolve_root.py", "set-root", "--root", str(target))
    cp = run_script("resolve_root.py", "get-root")
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(target)


def test_get_root_env_beats_config(run_script, fake_home, tmp_path):
    cfg_target = tmp_path / "cfg-specs"
    cfg_target.mkdir()
    run_script("resolve_root.py", "set-root", "--root", str(cfg_target))
    env_target = tmp_path / "env-specs"
    env_target.mkdir()
    cp = run_script("resolve_root.py", "get-root",
                    extra_env={"SPECODE_ROOT": str(env_target)})
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(env_target)


def test_list_specs_lists_dirs_with_requirements(run_script, fake_home, tmp_path):
    root = tmp_path / "specs-root"
    (root / "login").mkdir(parents=True)
    (root / "login" / "requirements.md").write_text("# login", encoding="utf-8")
    (root / "payment").mkdir()
    (root / "payment" / "requirements.md").write_text("# payment", encoding="utf-8")
    (root / "not-a-spec").mkdir()  # no requirements.md → excluded
    run_script("resolve_root.py", "set-root", "--root", str(root))
    cp = run_script("resolve_root.py", "list-specs")
    assert cp.returncode == 0, cp.stderr
    slugs = set(cp.stdout.split())
    assert slugs == {"login", "payment"}


def test_list_specs_unconfigured_exits_3(run_script, fake_home):
    cp = run_script("resolve_root.py", "list-specs")
    assert cp.returncode == 3, cp.stderr


def test_get_root_flag_beats_env(run_script, fake_home, tmp_path):
    flag_target = tmp_path / "flag-specs"
    flag_target.mkdir()
    cp = run_script("resolve_root.py", "get-root", "--root", str(flag_target),
                    extra_env={"SPECODE_ROOT": str(tmp_path / "env-specs")})
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(flag_target)


def test_get_root_unparseable_config_falls_through(run_script, fake_home, tmp_path):
    cfgp = fake_home / ".config" / "specode" / "config.json"
    cfgp.parent.mkdir(parents=True, exist_ok=True)
    cfgp.write_text("42", encoding="utf-8")  # 合法 JSON 但非 dict
    cp = run_script("resolve_root.py", "get-root")
    assert cp.returncode == 3, cp.stderr  # 非 dict → 视为空配置 → 未配置 exit 3


def test_get_root_falls_back_to_legacy_obsidian_root(run_script, fake_home, tmp_path):
    # 1.0.0 前的旧键 obsidianRoot：读端兜底，老用户升级即用
    cfgp = fake_home / ".config" / "specode" / "config.json"
    cfgp.parent.mkdir(parents=True, exist_ok=True)
    legacy = tmp_path / "legacy-specs"
    cfgp.write_text(json.dumps({"obsidianRoot": str(legacy)}), encoding="utf-8")
    cp = run_script("resolve_root.py", "get-root")
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(legacy)


def test_get_root_specsroot_beats_legacy_obsidian_root(run_script, fake_home, tmp_path):
    cfgp = fake_home / ".config" / "specode" / "config.json"
    cfgp.parent.mkdir(parents=True, exist_ok=True)
    cfgp.write_text(json.dumps({
        "specsRoot": str(tmp_path / "new-specs"),
        "obsidianRoot": str(tmp_path / "old-specs"),
    }), encoding="utf-8")
    cp = run_script("resolve_root.py", "get-root")
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(tmp_path / "new-specs")
