"""End-to-end CLI test for task_swarm.py.

Walks the protocol: init → next (fork coder) → write fake outbox → parse →
advance → next (fork reviewer) → ... → writeback → next (done).

Verifies the JSON contracts that the orchestrator (main Claude session)
depends on.
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import task_swarm as TS  # noqa: E402


TASKS_MD = """\
# 任务

- [ ] 1. 实现 A
  - [ ] 1.1 写 a
    - 文件：src/a.py
    - _需求：1.1_

- [ ] 2. 检查点
  - 运行 pytest
"""


def _run(argv: list[str]) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = TS.main(argv)
    text = buf.getvalue().strip()
    assert rc == 0, f"cmd failed: {' '.join(argv)} stdout={text}"
    return json.loads(text)


def _setup_workspace() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="ts-cli-"))
    spec = tmp / "spec-dir"
    spec.mkdir()
    project = tmp / "project"
    project.mkdir()
    (spec / "tasks.md").write_text(TASKS_MD, encoding="utf-8")
    return {"tmp": tmp, "spec": spec, "project": project, "tasks": spec / "tasks.md"}


def _cleanup(ws):
    shutil.rmtree(ws["tmp"], ignore_errors=True)


def test_full_cli_flow_happy_path():
    ws = _setup_workspace()
    try:
        # init
        init_out = _run([
            "init",
            "--tasks", str(ws["tasks"]),
            "--project-root", str(ws["project"]),
            "--max-rounds", "3",
            "--parallel", "2",
        ])
        run_id = init_out["run_id"]
        assert len(init_out["stages"]) == 2

        # next → fork stage 1 coder
        nxt = _run(["next", "--run", run_id, "--project-root", str(ws["project"])])
        assert nxt["action"] == "fork"
        assert nxt["stage"] == 1
        assert nxt["role"] == "coder"
        assert nxt["subagent_type"] == "specode:task-swarm-coder"
        prompt_file = Path(nxt["prompt_file"])
        assert prompt_file.exists()
        assert "CODER" in prompt_file.read_text()
        workspace = Path(nxt["workspace"])

        # simulate coder writing result.md
        (workspace / "outbox" / "result.md").write_text(
            "# 阶段 1 结果\n\n"
            "## 子任务状态\n"
            "- 1.1 写 a: done — src/a.py\n\n"
            "## 关键变更\n- 新增 A\n\nSTATUS: ok\n",
            encoding="utf-8",
        )

        # parse
        parsed = _run([
            "parse", "--run", run_id,
            "--stage", "1", "--role", "coder", "--round", "1",
            "--project-root", str(ws["project"]),
        ])
        assert parsed["judgment"] == "ok"

        # advance
        _run([
            "advance", "--run", run_id,
            "--stage", "1", "--role", "coder", "--round", "1",
            "--judgment", "ok",
            "--project-root", str(ws["project"]),
        ])

        # next → fork stage 1 reviewer
        nxt = _run(["next", "--run", run_id, "--project-root", str(ws["project"])])
        assert nxt["action"] == "fork"
        assert nxt["role"] == "reviewer"
        rev_ws = Path(nxt["workspace"])
        # reviewer's inbox should contain coder's result.md (relayed)
        assert (rev_ws / "inbox" / "result.md").exists()

        # simulate reviewer approving
        (rev_ws / "outbox" / "review.md").write_text(
            "## 结论\napproved\n\n"
            "## P0 — 阻塞，coder 必须修复（修完才能进 validator）\n(none)\n\n"
            "## P1 — 建议修复，不阻塞\n- 命名\n\n"
            "## P2 — 可选改进\n- 风格\n\nSTATUS: ok\n",
            encoding="utf-8",
        )
        parsed = _run([
            "parse", "--run", run_id,
            "--stage", "1", "--role", "reviewer", "--round", "1",
            "--project-root", str(ws["project"]),
        ])
        assert parsed["judgment"] == "approved"
        _run([
            "advance", "--run", run_id,
            "--stage", "1", "--role", "reviewer", "--round", "1",
            "--judgment", "approved",
            "--project-root", str(ws["project"]),
        ])

        # next → writeback stage 1
        nxt = _run(["next", "--run", run_id, "--project-root", str(ws["project"])])
        assert nxt["action"] == "writeback"
        assert nxt["stage"] == 1

        # writeback
        wb_out = _run([
            "writeback", "--run", run_id, "--stage", "1",
            "--project-root", str(ws["project"]),
        ])
        assert wb_out["written"] is True
        tasks_text = ws["tasks"].read_text(encoding="utf-8")
        assert "- [x] 1. 实现 A" in tasks_text
        assert "- [x] 1.1 写 a" in tasks_text
        # annotation appended
        assert "task-swarm 收敛" in tasks_text
        # metadata preserved
        assert "_需求：1.1_" in tasks_text
        assert "文件：src/a.py" in tasks_text

        # next → fork checkpoint validator
        nxt = _run(["next", "--run", run_id, "--project-root", str(ws["project"])])
        assert nxt["action"] == "fork"
        assert nxt["role"] == "validator"
        v_ws = Path(nxt["workspace"])

        (v_ws / "outbox" / "validation.md").write_text(
            "## 判定\npass\n\n"
            "## 复现命令\n```bash\npytest\n```\n\n"
            "## 按子任务的验证结果\n- [x] 1.1 a: pass\n\nSTATUS: ok\n",
            encoding="utf-8",
        )
        parsed = _run([
            "parse", "--run", run_id,
            "--stage", "2", "--role", "validator", "--round", "1",
            "--project-root", str(ws["project"]),
        ])
        assert parsed["judgment"] == "pass"
        _run([
            "advance", "--run", run_id,
            "--stage", "2", "--role", "validator", "--round", "1",
            "--judgment", "pass",
            "--project-root", str(ws["project"]),
        ])

        # next → writeback stage 2
        nxt = _run(["next", "--run", run_id, "--project-root", str(ws["project"])])
        assert nxt["action"] == "writeback"
        _run([
            "writeback", "--run", run_id, "--stage", "2",
            "--project-root", str(ws["project"]),
        ])

        # next → done
        nxt = _run(["next", "--run", run_id, "--project-root", str(ws["project"])])
        assert nxt["action"] == "done"
        assert "summary" in nxt
    finally:
        _cleanup(ws)


def test_init_creates_active_run_pointer():
    ws = _setup_workspace()
    try:
        out = _run([
            "init",
            "--tasks", str(ws["tasks"]),
            "--project-root", str(ws["project"]),
        ])
        pointer = ws["project"] / ".task-swarm" / "active-run"
        assert pointer.exists()
        assert pointer.read_text().strip() == out["run_id"]
    finally:
        _cleanup(ws)


def test_writeback_rejects_unconverged_stage():
    ws = _setup_workspace()
    try:
        out = _run([
            "init",
            "--tasks", str(ws["tasks"]),
            "--project-root", str(ws["project"]),
        ])
        run_id = out["run_id"]
        # No advance — stage 1 is still pending; writeback should error.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = TS.main([
                "writeback", "--run", run_id, "--stage", "1",
                "--project-root", str(ws["project"]),
            ])
        assert rc == 2
        body = json.loads(buf.getvalue())
        assert "尚未收敛" in body["error"] or "phase=pending" in body["error"]
    finally:
        _cleanup(ws)
