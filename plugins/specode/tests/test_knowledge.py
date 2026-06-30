"""knowledge.py CLI tests — hermetic, subprocess-driven (mirrors test_resolve_root)."""
from __future__ import annotations

from pathlib import Path


def _write_doc(kb: Path, rel: str, *, 标题, 类型, 来源="", tags=None, 描述=""):
    p = kb / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    taglist = "[" + ", ".join(tags or []) + "]"
    fm = (
        "---\n"
        f"标题: {标题}\n"
        f"类型: {类型}\n"
        f"来源: {来源}\n"
        f"tags: {taglist}\n"
        f"描述: {描述}\n"
        "---\n\n# body\n"
    )
    p.write_text(fm, encoding="utf-8")


def test_memory_rebuild_two_docs_sorted(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "navigation/list-locate.md", 标题="查询列表定位路径",
               类型="navigation", 来源="需求2", tags=["查询列表", "B页面"], 描述="列表页定位套路")
    _write_doc(kb, "cases/a-page-bank-mask.md", 标题="A页面银行账号脱敏改法",
               类型="case", 来源="需求1", tags=["银行账号", "脱敏", "A页面"], 描述="前端列+后端DTO脱敏")
    res = run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    mem = (kb / "MEMORY.md").read_text(encoding="utf-8")
    assert "| 标题 | 类型 | 描述 | 来源 | 路径 | tags |" in mem
    # case 排在 navigation 前（类型升序），路径用相对 kb 的 POSIX
    case_idx = mem.index("cases/a-page-bank-mask.md")
    nav_idx = mem.index("navigation/list-locate.md")
    assert case_idx < nav_idx
    assert "银行账号,脱敏,A页面" in mem  # tags 以逗号连接


def test_memory_rebuild_excludes_memory_itself(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case")
    (kb / "MEMORY.md").write_text("stale\n", encoding="utf-8")
    res = run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    mem = (kb / "MEMORY.md").read_text(encoding="utf-8")
    assert "MEMORY.md" not in mem  # 不索引自身
    assert "cases/x.md" in mem


def test_memory_rebuild_skips_malformed(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/good.md", 标题="Good", 类型="case")
    (kb / "cases" / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")
    res = run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    mem = (kb / "MEMORY.md").read_text(encoding="utf-8")
    assert "cases/good.md" in mem
    assert "cases/bad.md" not in mem


def test_ensure_gitignore_creates_file_in_git_repo(run_script, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()  # a git repo -> .gitignore is meaningful
    res = run_script("knowledge.py", "ensure-gitignore", "--project-root", str(proj))
    assert res.returncode == 0, res.stderr
    gi = proj / ".gitignore"
    assert gi.exists()
    assert "knowledge-base/" in gi.read_text(encoding="utf-8").splitlines()


def test_ensure_gitignore_skips_when_no_git_no_gitignore(run_script, tmp_path: Path):
    # F3: non-git project with no existing .gitignore -> don't create a stray file
    proj = tmp_path / "proj"
    proj.mkdir()
    res = run_script("knowledge.py", "ensure-gitignore", "--project-root", str(proj))
    assert res.returncode == 0, res.stderr
    assert not (proj / ".gitignore").exists()


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


def test_memory_validate_clean(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case")
    run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    res = run_script("knowledge.py", "memory-validate", "--kb", str(kb))
    assert res.returncode == 0, res.stderr


def test_memory_validate_detects_unindexed(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case")
    run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    _write_doc(kb, "cases/y.md", 标题="Y", 类型="case")  # added after rebuild
    res = run_script("knowledge.py", "memory-validate", "--kb", str(kb))
    assert res.returncode == 2
    assert "cases/y.md" in (res.stdout + res.stderr)


def test_memory_validate_detects_dangling(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case")
    run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    (kb / "cases" / "x.md").unlink()  # removed after rebuild
    res = run_script("knowledge.py", "memory-validate", "--kb", str(kb))
    assert res.returncode == 2
    assert "cases/x.md" in (res.stdout + res.stderr)


# Fix 2: pipe character in 描述 must not corrupt the MEMORY table
def test_memory_validate_pipe_in_description(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/pipe.md", 标题="管道测试", 类型="case", 描述="前端|后端")
    res = run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    mem = (kb / "MEMORY.md").read_text(encoding="utf-8")
    # Each data row must have exactly len(_COLS) cells
    for line in mem.splitlines():
        if line.startswith("| ") and "| 标题 |" not in line and "---" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            assert len(cells) == 6, f"wrong cell count: {line!r}"
    res2 = run_script("knowledge.py", "memory-validate", "--kb", str(kb))
    assert res2.returncode == 0, res2.stdout + res2.stderr


# Fix 3: triple-dash in 描述 must not be mistaken for a table separator
def test_memory_validate_dashes_in_description(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/dash.md", 标题="横杠测试", 类型="case", 描述="前端---后端")
    res = run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    res2 = run_script("knowledge.py", "memory-validate", "--kb", str(kb))
    assert res2.returncode == 0, res2.stdout + res2.stderr


# Fix 4: tags as plain comma-string (no brackets) must be indexed correctly
def test_memory_rebuild_comma_string_tags(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    # Write frontmatter directly — _write_doc always brackets the tag list
    p = kb / "cases" / "tag-plain.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        "标题: 平铺标签测试\n"
        "类型: case\n"
        "来源: 需求X\n"
        "tags: 银行账号, 脱敏\n"
        "描述: 无括号逗号标签\n"
        "---\n\n# body\n",
        encoding="utf-8",
    )
    res = run_script("knowledge.py", "memory-rebuild", "--kb", str(kb))
    assert res.returncode == 0, res.stderr
    mem = (kb / "MEMORY.md").read_text(encoding="utf-8")
    assert "银行账号,脱敏" in mem


# --- copy-to (F4: one-step dual-landing — cp cases/navigation + rebuild MEMORY on dest) ---


def test_copy_to_copies_and_rebuilds(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case", tags=["t"])
    _write_doc(kb, "navigation/y.md", 标题="Y", 类型="navigation", tags=["t"])
    (kb / "MEMORY.md").write_text("stale\n", encoding="utf-8")  # src MEMORY is irrelevant
    dest = tmp_path / "obsidian-copy"
    res = run_script("knowledge.py", "copy-to", "--kb", str(kb), "--dest", str(dest))
    assert res.returncode == 0, res.stderr
    assert (dest / "cases" / "x.md").exists()
    assert (dest / "navigation" / "y.md").exists()
    mem = (dest / "MEMORY.md").read_text(encoding="utf-8")
    assert "| 标题 | 类型 | 描述 | 来源 | 路径 | tags |" in mem
    assert "cases/x.md" in mem and "navigation/y.md" in mem


def test_copy_to_rejects_relative_dest(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case")
    res = run_script("knowledge.py", "copy-to", "--kb", str(kb), "--dest", "rel/dir")
    assert res.returncode == 1, res.stderr


def test_copy_to_creates_missing_dest(run_script, tmp_path: Path):
    kb = tmp_path / "knowledge-base"
    _write_doc(kb, "cases/x.md", 标题="X", 类型="case")
    dest = tmp_path / "newdir" / "kb-copy"  # does not exist yet
    res = run_script("knowledge.py", "copy-to", "--kb", str(kb), "--dest", str(dest))
    assert res.returncode == 0, res.stderr
    assert (dest / "cases" / "x.md").exists()
