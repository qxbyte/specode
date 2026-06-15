"""Tests for spec_init.py -n 目录已存在三态处理（0.10.27+）。

三态语义：
  * 空目录          → 正常 init（用户提前 mkdir 占位）
  * 含 .config.json → fallback 到 cmd_continue 接管（保留既有 source_text）
  * 脏目录          → exit 3 报错（避免污染既有非 specode 内容）

不同 session 触发锁冲突已在 test_spec_init.py 用例覆盖；本文件聚焦三态分支本身。
"""
from __future__ import annotations

import json
from pathlib import Path


def test_empty_directory_proceeds_to_normal_init(
    run_script, doc_root, make_session_id
):
    """用户提前 mkdir 占位 → spec_init 仍能成功创建文档。"""
    pre_existing = doc_root / "specs" / "empty-precreate"
    pre_existing.mkdir(parents=True)
    assert pre_existing.exists() and not any(pre_existing.iterdir())

    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "empty-precreate",
        "--requirement-name", "Empty Pre",
        "--source-text", "占位目录测试",
        "--session", sid,
    )
    assert cp.returncode == 0, cp.stderr
    cfg = json.loads((pre_existing / ".config.json").read_text("utf-8"))
    assert cfg["slug"] == "empty-precreate"
    assert cfg["source_text"] == "占位目录测试"
    # 4 份文档应被创建（M4 起不再产 tasks.md）
    for fname in ("requirements.md", "bugfix.md", "design.md",
                  "implementation-log.md"):
        assert (pre_existing / fname).exists(), fname
    assert not (pre_existing / "tasks.md").exists()


def test_existing_dir_with_config_same_session_falls_back_to_continue(
    run_script, doc_root, make_session_id
):
    """同 session 重新 spec_init 同 slug → fallback 到 cmd_continue 接管成功（exit 0）。

    既有 .config.json 不被覆盖：specId / source_text 都保留。
    """
    sid = make_session_id()
    cp1 = run_script(
        "spec_init.py",
        "--name", "same-sid",
        "--requirement-name", "First Name",
        "--source-text", "首次 source",
        "--session", sid,
    )
    assert cp1.returncode == 0, cp1.stderr
    first_cfg = json.loads(
        (doc_root / "specs" / "same-sid" / ".config.json").read_text("utf-8")
    )

    cp2 = run_script(
        "spec_init.py",
        "--name", "same-sid",
        "--requirement-name", "Second Name",
        "--source-text", "覆盖企图——应被丢弃",
        "--session", sid,
    )
    # 同 session 抢锁成功 → cmd_continue exit 0
    assert cp2.returncode == 0, cp2.stderr
    assert "fallback" in cp2.stderr
    body = json.loads(cp2.stdout)
    assert body["ok"] is True
    assert body["spec_dir"].endswith("same-sid")

    again_cfg = json.loads(
        (doc_root / "specs" / "same-sid" / ".config.json").read_text("utf-8")
    )
    assert again_cfg["specId"] == first_cfg["specId"]
    # source_text 保留既有 — 第二次的"覆盖企图"未生效
    assert again_cfg["source_text"] == first_cfg["source_text"] == "首次 source"


def test_dirty_directory_refuses_with_exit_3(
    run_script, doc_root, make_session_id
):
    """目录已存在但缺 .config.json + 含其它文件 → exit 3 报错（保护非 specode 内容）。"""
    dirty = doc_root / "specs" / "dirty-dir"
    dirty.mkdir(parents=True)
    (dirty / "random.txt").write_text("user data", encoding="utf-8")
    (dirty / "notes.md").write_text("# whatever", encoding="utf-8")
    # 确保没有 .config.json
    assert not (dirty / ".config.json").exists()

    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "dirty-dir",
        "--requirement-name", "Dirty",
        "--source-text", "won't run",
        "--session", sid,
    )
    assert cp.returncode == 3
    assert "脏目录" in cp.stderr
    # 既有文件未被动
    assert (dirty / "random.txt").read_text("utf-8") == "user data"
    assert (dirty / "notes.md").read_text("utf-8") == "# whatever"
    # 没创建 .config.json
    assert not (dirty / ".config.json").exists()


def test_dirty_directory_listing_lists_first_files(
    run_script, doc_root, make_session_id
):
    """stderr 错误信息列出脏目录内的文件名，方便用户诊断。"""
    dirty = doc_root / "specs" / "many-files"
    dirty.mkdir(parents=True)
    for i in range(8):
        (dirty / f"file-{i}.txt").write_text(f"content {i}", encoding="utf-8")

    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "many-files",
        "--requirement-name", "Many",
        "--source-text", "many",
        "--session", sid,
    )
    assert cp.returncode == 3
    # 至少显示前 5 个文件名 + "+N more" 标记
    assert "file-" in cp.stderr
    assert "more" in cp.stderr
