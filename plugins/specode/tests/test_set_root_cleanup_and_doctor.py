"""Tests for v0.9 痛点 #8 + #9 — set-root key cleanup + doctor verb.

#8: set-root used to write `specsRoot` without removing the legacy
    `obsidianRoot` key (specode <1.0.0), leaving both in the JSON.
    Other plugins that still read `obsidianRoot` then point at the
    *old* path → silent split-brain (real incident 2026-06-28).

#9: There was no way to detect "vault directory was renamed by the
    user, config still points at the old path". A new `doctor` verb
    surfaces this immediately, with a suggested set-root fix line.
"""

from __future__ import annotations

import json
from pathlib import Path


def _read_config(fake_home: Path) -> dict:
    config_file = fake_home / ".config" / "specode" / "config.json"
    if not config_file.is_file():
        return {}
    return json.loads(config_file.read_text(encoding="utf-8"))


def _seed_config(fake_home: Path, payload: dict) -> Path:
    config_dir = fake_home / ".config" / "specode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    return config_file


# ---------- #8: set-root cleans legacy obsidianRoot key ----------


def test_set_root_removes_legacy_obsidianRoot(run_script, fake_home, tmp_path):
    """v0.9 痛点 #8: set-root should strip the legacy obsidianRoot key
    so other plugins (obsidian-wiki etc.) don't silently read a stale
    path after the user moves their vault."""
    new_root = tmp_path / "NewSpecs"
    new_root.mkdir()
    # Pretend an old-school user has both keys set, obsidianRoot pointing
    # at a now-renamed dir.
    _seed_config(
        fake_home,
        {
            "vaultPath": str(tmp_path),
            "obsidianRoot": str(tmp_path / "OldSpecs"),  # legacy / stale
            "specsRoot": str(tmp_path / "OldSpecs"),
        },
    )

    result = run_script("resolve_root.py", "set-root", "--root", str(new_root))
    assert result.returncode == 0, result.stderr

    cfg = _read_config(fake_home)
    assert cfg["specsRoot"] == str(new_root)
    assert "obsidianRoot" not in cfg, (
        f"obsidianRoot legacy key should have been removed, got: {cfg}"
    )
    # Non-conflicting keys must be preserved.
    assert cfg.get("vaultPath") == str(tmp_path)


def test_set_root_first_time_no_legacy(run_script, fake_home, tmp_path):
    """Fresh user (no config yet) — set-root creates clean config with only
    specsRoot. No obsidianRoot ever written."""
    new_root = tmp_path / "MySpecs"
    new_root.mkdir()
    result = run_script("resolve_root.py", "set-root", "--root", str(new_root))
    assert result.returncode == 0

    cfg = _read_config(fake_home)
    assert cfg == {"specsRoot": str(new_root)}, (
        f"first-time config should be minimal, got: {cfg}"
    )


# ---------- #9: doctor verb ----------


def test_doctor_passes_when_specsRoot_exists(run_script, fake_home, tmp_path):
    """doctor: configured + dir exists → exit 0 + happy line."""
    specs_root = tmp_path / "Specs"
    specs_root.mkdir()
    _seed_config(fake_home, {"specsRoot": str(specs_root)})

    result = run_script("resolve_root.py", "doctor")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "ok" in out.lower() or "✓" in out
    assert str(specs_root) in out


def test_doctor_fails_when_specsRoot_not_set(run_script, fake_home, tmp_path):
    """doctor: config missing entirely → exit 3 + 'run set-root' hint."""
    result = run_script("resolve_root.py", "doctor")
    assert result.returncode == 3
    msg = result.stderr + result.stdout
    assert "set-root" in msg.lower(), f"should suggest set-root, got: {msg!r}"


def test_doctor_fails_when_specsRoot_dir_does_not_exist(
    run_script, fake_home, tmp_path
):
    """doctor: config points at a path that no longer exists (user renamed
    the vault directory) → exit 4 + actionable suggestion line."""
    missing = tmp_path / "RenamedAway"
    # do NOT mkdir
    _seed_config(fake_home, {"specsRoot": str(missing)})

    result = run_script("resolve_root.py", "doctor")
    assert result.returncode == 4
    msg = result.stderr + result.stdout
    assert str(missing) in msg
    # message can be either Chinese or English; both must indicate "missing"
    msg_lower = msg.lower()
    assert (
        "不存在" in msg
        or "missing" in msg_lower
        or "not exist" in msg_lower
        or "not found" in msg_lower
    ), f"should indicate dir missing, got: {msg!r}"
    # Should give the user a copy-pasteable fix command.
    assert "set-root --root" in msg


def test_doctor_warns_when_legacy_obsidianRoot_present(
    run_script, fake_home, tmp_path
):
    """v0.9 痛点 #8 + #9 combined: even if specsRoot is fine, doctor should
    warn when the legacy obsidianRoot key is still hanging around (will be
    silently read by old plugins → split-brain risk). Suggests one set-root
    call to clean it up."""
    specs_root = tmp_path / "Specs"
    specs_root.mkdir()
    _seed_config(
        fake_home,
        {
            "specsRoot": str(specs_root),
            "obsidianRoot": str(tmp_path / "OldSpecs"),  # legacy stale
        },
    )

    result = run_script("resolve_root.py", "doctor")
    # Exit code is still 0 (not a hard failure — specsRoot works), but
    # stdout / stderr must surface the warning so the user notices.
    assert result.returncode == 0
    blob = result.stdout + result.stderr
    assert "obsidianRoot" in blob
    assert "legacy" in blob.lower() or "stale" in blob.lower() or "set-root" in blob.lower()
