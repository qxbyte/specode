"""Tests for project_root verbs in resolve_root.py (FIX-1: single source of truth).

project_root is the join key between a spec (under specsRoot) and the project
whose .ai-memory/knowledge it feeds. It lives in exactly one place — the spec's
requirements.md YAML frontmatter — and every consumer reads it through the same
``read-project-root`` entry. ``write-project-root`` is the single validated
writer. ``resolve-project-root`` computes the default for the host agent to
confirm.
"""
from __future__ import annotations

from pathlib import Path

FRONTMATTER = """---
spec_id: my-spec
project_root: {root}
created_at: 2026-06-27
---

# My spec

body
"""


def _make_spec(specs_root: Path, slug: str, project_root: str | None) -> Path:
    spec_dir = specs_root / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    if project_root is None:
        body = "---\nspec_id: my-spec\ncreated_at: 2026-06-27\n---\n\n# spec\n"
    else:
        body = FRONTMATTER.format(root=project_root)
    (spec_dir / "requirements.md").write_text(body, encoding="utf-8")
    return spec_dir


# ---------- read-project-root ----------


def test_read_project_root_from_spec_dir(run_script, fake_home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    spec_dir = _make_spec(tmp_path / "specs", "login", str(proj))
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(proj)


def test_read_project_root_accepts_requirements_path(run_script, fake_home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    spec_dir = _make_spec(tmp_path / "specs", "login", str(proj))
    req = spec_dir / "requirements.md"
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(req))
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(proj)


def test_read_project_root_missing_field_exits_3(run_script, fake_home, tmp_path):
    spec_dir = _make_spec(tmp_path / "specs", "login", None)
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp.returncode == 3, cp.stdout + cp.stderr


def test_read_project_root_no_requirements_exits_3(run_script, fake_home, tmp_path):
    spec_dir = tmp_path / "specs" / "empty"
    spec_dir.mkdir(parents=True)
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp.returncode == 3, cp.stdout + cp.stderr


def test_read_project_root_nonexistent_dir_exits_4(run_script, fake_home, tmp_path):
    spec_dir = _make_spec(tmp_path / "specs", "login", str(tmp_path / "does-not-exist"))
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp.returncode == 4, cp.stdout + cp.stderr


def test_read_project_root_relative_value_exits_4(run_script, fake_home, tmp_path):
    spec_dir = _make_spec(tmp_path / "specs", "login", "relative/proj")
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp.returncode == 4, cp.stdout + cp.stderr


# ---------- write-project-root ----------


def test_write_project_root_inserts_into_existing_frontmatter(run_script, fake_home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    spec_dir = _make_spec(tmp_path / "specs", "login", None)  # frontmatter w/o project_root
    cp = run_script("resolve_root.py", "write-project-root",
                    "--spec", str(spec_dir), "--root", str(proj))
    assert cp.returncode == 0, cp.stderr
    # read back through the single read entry
    cp2 = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp2.returncode == 0, cp2.stderr
    assert cp2.stdout.strip() == str(proj)


def test_write_project_root_updates_existing_value(run_script, fake_home, tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    new = tmp_path / "new"
    new.mkdir()
    spec_dir = _make_spec(tmp_path / "specs", "login", str(old))
    cp = run_script("resolve_root.py", "write-project-root",
                    "--spec", str(spec_dir), "--root", str(new))
    assert cp.returncode == 0, cp.stderr
    text = (spec_dir / "requirements.md").read_text(encoding="utf-8")
    assert str(new) in text
    assert text.count("project_root:") == 1  # updated in place, not duplicated


def test_write_project_root_preserves_body_and_other_fields(run_script, fake_home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    spec_dir = _make_spec(tmp_path / "specs", "login", None)
    run_script("resolve_root.py", "write-project-root",
               "--spec", str(spec_dir), "--root", str(proj))
    text = (spec_dir / "requirements.md").read_text(encoding="utf-8")
    assert "spec_id: my-spec" in text
    assert "created_at: 2026-06-27" in text
    assert "# spec" in text


def test_write_project_root_creates_frontmatter_when_absent(run_script, fake_home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    spec_dir = tmp_path / "specs" / "login"
    spec_dir.mkdir(parents=True)
    (spec_dir / "requirements.md").write_text("# spec no frontmatter\n\nbody\n", encoding="utf-8")
    cp = run_script("resolve_root.py", "write-project-root",
                    "--spec", str(spec_dir), "--root", str(proj))
    assert cp.returncode == 0, cp.stderr
    cp2 = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp2.returncode == 0, cp2.stderr
    assert cp2.stdout.strip() == str(proj)
    assert "# spec no frontmatter" in (spec_dir / "requirements.md").read_text(encoding="utf-8")


def test_write_project_root_rejects_relative(run_script, fake_home, tmp_path):
    spec_dir = _make_spec(tmp_path / "specs", "login", None)
    cp = run_script("resolve_root.py", "write-project-root",
                    "--spec", str(spec_dir), "--root", "relative/proj")
    assert cp.returncode == 1, cp.stdout + cp.stderr


def test_write_project_root_rejects_nonexistent_dir(run_script, fake_home, tmp_path):
    spec_dir = _make_spec(tmp_path / "specs", "login", None)
    cp = run_script("resolve_root.py", "write-project-root",
                    "--spec", str(spec_dir), "--root", str(tmp_path / "nope"))
    assert cp.returncode == 1, cp.stdout + cp.stderr


# ---------- resolve-project-root (default computation) ----------


def test_resolve_project_root_defaults_to_cwd_when_no_git(run_script, fake_home, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    cp = run_script("resolve_root.py", "resolve-project-root", "--cwd", str(plain))
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == str(plain)


# ---------- red line: external-drive mount check ----------


def test_read_project_root_unmounted_volume_exits_4(run_script, fake_home, tmp_path):
    # project_root under an unmounted /Volumes/<name> → refuse (no silent fallback)
    spec_dir = _make_spec(tmp_path / "specs", "login", "/Volumes/NoSuchDrive-xyz/proj")
    cp = run_script("resolve_root.py", "read-project-root", "--spec", str(spec_dir))
    assert cp.returncode == 4, cp.stdout + cp.stderr


def test_write_project_root_rejects_unmounted_volume(run_script, fake_home, tmp_path):
    spec_dir = _make_spec(tmp_path / "specs", "login", None)
    cp = run_script("resolve_root.py", "write-project-root",
                    "--spec", str(spec_dir), "--root", "/Volumes/NoSuchDrive-xyz/proj")
    assert cp.returncode == 1, cp.stdout + cp.stderr
