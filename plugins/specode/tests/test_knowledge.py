"""knowledge.py CLI tests — hermetic, subprocess-driven (mirrors test_resolve_root)."""
from __future__ import annotations

from pathlib import Path


def test_ensure_gitignore_creates_file(run_script, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    res = run_script("knowledge.py", "ensure-gitignore", "--project-root", str(proj))
    assert res.returncode == 0, res.stderr
    gi = proj / ".gitignore"
    assert gi.exists()
    assert "knowledge-base/" in gi.read_text(encoding="utf-8").splitlines()


def test_ensure_gitignore_idempotent(run_script, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".gitignore").write_text("node_modules/\nknowledge-base/\n", encoding="utf-8")
    res = run_script("knowledge.py", "ensure-gitignore", "--project-root", str(proj))
    assert res.returncode == 0, res.stderr
    lines = (proj / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count("knowledge-base/") == 1
    assert "node_modules/" in lines  # preserves existing


def test_ensure_gitignore_appends_preserving(run_script, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".gitignore").write_text("dist/\n", encoding="utf-8")
    res = run_script("knowledge.py", "ensure-gitignore", "--project-root", str(proj))
    assert res.returncode == 0, res.stderr
    lines = (proj / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "dist/" in lines and "knowledge-base/" in lines
