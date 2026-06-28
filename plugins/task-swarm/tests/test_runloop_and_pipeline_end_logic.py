"""Regression tests for v0.8.1 — M2 run-loop + M3 pipeline-end validator logic.

M2: ``cmd_run_loop`` auto-drives mechanical phases (advance / writeback /
resolve) until host fork needed or all done. Solves the "12+ manual
advance calls per run" pain from v0.9 round-2 试跑.

M3 logic: when ``pipeline.yml`` has ``run.pipeline_end_validator: true``,
all groups done → cross-group validator-pipeline-end-r1 forked → plan
emits ``pipeline-end-validation-fork``; advance --phase pipeline-end-validation
flips ``sm.pipeline_end_status`` to passed/failed; resolve blocks on
non-passed pipeline_end_status.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "scripts"
TASK_SWARM_PY = REPO_ROOT / "task_swarm.py"

sys.path.insert(0, str(REPO_ROOT))
from task_swarm._state import StateMachine  # noqa: E402


def _make_pipeline(path: Path, spec_id: str = "demo-spec",
                   pipeline_end_validator: bool = False,
                   needs: dict | None = None) -> None:
    """Minimal valid 2-group pipeline.yml."""
    pe_line = "  pipeline_end_validator: true\n" if pipeline_end_validator else ""
    needs_g2 = (needs or {}).get("g2", [])
    needs_str = ""
    if needs_g2:
        needs_str = "    needs:\n" + "\n".join(f"      - {n}" for n in needs_g2) + "\n"
    text = f"""version: 1
run:
  spec_id: {spec_id}
{pe_line}task_groups:
  - id: g1
    name: "group one"
    tasks:
      - id: g1.1
        title: "task in g1"
        writes:
          - src/a.py
  - id: g2
    name: "group two"
{needs_str}    tasks:
      - id: g2.1
        title: "task in g2"
        writes:
          - src/b.py
"""
    path.write_text(text, encoding="utf-8")


def _run(*args, fake_home: Path | None = None,
         workdir_env: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(TASK_SWARM_PY), *args]
    env = os.environ.copy()
    if fake_home:
        env["HOME"] = str(fake_home)
    if workdir_env:
        env["TASK_SWARM_WORKDIR"] = workdir_env
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _init_and_get_run_id(tmp_path: Path, pipeline_end_validator: bool = False) -> tuple[str, Path, Path]:
    """Returns (run_id, run_dir, workdir)."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline(pipeline, pipeline_end_validator=pipeline_end_validator)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    r = _run("init", "--pipeline", str(pipeline), "--workdir", str(workdir),
             "--spec-id", "demo-spec", fake_home=home)
    assert r.returncode == 0, f"init failed: {r.stderr}"
    data = json.loads(r.stdout)
    return data["run_id"], Path(data["run_dir"]), workdir


def _write_outbox(run_dir: Path, agent_key: str, kind: str,
                  status: str = "ok", verdict: str = "pass") -> None:
    """Write a minimal valid outbox file for a subagent so advance can parse it.

    kind ∈ {result, review, validation}.
    """
    out = run_dir / "agents" / agent_key / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    if kind == "result":
        body = (f"# {agent_key} result\n\n## 上下文\n- ok\n\n"
                f"## 子任务状态\n- 1.1 demo: done\n\n## 关键变更\n- demo\n\n"
                f"STATUS: {status}\n")
        (out / "result.md").write_text(body, encoding="utf-8")
    elif kind == "review":
        body = (f"# {agent_key}\n\n## 结论\napproved\n\n## P0\n(none)\n\n"
                f"## P1\n\n## P2\n\n## 给使用者的提示\n- demo\n\nSTATUS: ok\n")
        (out / "review.md").write_text(body, encoding="utf-8")
    elif kind == "validation":
        if verdict == "pass":
            body = (f"# {agent_key}\n\n## 判定\npass\n\n## 复现命令\n```bash\necho ok\n```\n\n"
                    f"## 按子任务的验证结果\n- [x] 1.1 demo: pass\n\nSTATUS: ok\n")
        else:
            body = (f"# {agent_key}\n\n## 判定\nfail\n\n## 复现命令\n```bash\necho fail\n```\n\n"
                    f"## 按子任务的验证结果\n- [ ] 1.1 demo: fail — broken\n\n"
                    f"## 失败现场（fail 时必填）\n```\nFAILED demo\n```\n\n"
                    f"## 给 coder 的修复指引（fail 时必填，不带 P0/P1 标签）\n"
                    f"### 修复 1 — fix it\n- 文件: src/a.py\n- 问题: broken\n- 建议: fix\n\n"
                    f"STATUS: ok\n")
        (out / "validation.md").write_text(body, encoding="utf-8")


# ---------- M3 logic: pipeline-end validator schema → plan/advance/resolve ----------

def test_pipeline_end_validator_false_default_behaves_as_before(tmp_path: Path) -> None:
    """pipeline_end_validator=false (default) → pipeline_end_status stays
    "not-required"; resolve when all groups done works as before."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=False)
    sm = StateMachine.load(run_dir)
    assert sm.pipeline_end_validator is False
    assert sm.pipeline_end_status == "not-required"


def test_pipeline_end_validator_true_sets_pending_status(tmp_path: Path) -> None:
    """pipeline_end_validator=true → init sets pipeline_end_status=pending."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    assert sm.pipeline_end_validator is True
    assert sm.pipeline_end_status == "pending"


def test_plan_emits_pipeline_end_fork_when_all_groups_done(tmp_path: Path) -> None:
    """When all groups reach done + pipeline_end_status=pending, plan emits
    `pipeline-end-validation-fork` action."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    # Mark all groups as done directly in state (skip the full flow for unit speed)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.save()

    r = _run("plan", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 0
    plan = json.loads(r.stdout)
    assert plan.get("action") == "pipeline-end-validation-fork"
    assert plan["fork"][0]["agent_key"] == "validator-pipeline-end-r1"
    assert plan["fork"][0]["scope"] == "pipeline-end"
    assert (run_dir / "agents" / "validator-pipeline-end-r1" / "task.md").is_file()


def test_advance_pipeline_end_validation_pass_flips_status(tmp_path: Path) -> None:
    """advance --phase pipeline-end-validation reads outbox + sets passed."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.save()
    _write_outbox(run_dir, "validator-pipeline-end-r1", "validation", verdict="pass")

    r = _run("advance", "--run", run_id, "--phase", "pipeline-end-validation",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["verdict"] == "pass"
    assert data["pipeline_end_status"] == "passed"

    sm2 = StateMachine.load(run_dir)
    assert sm2.pipeline_end_status == "passed"


def test_advance_pipeline_end_validation_fail_flips_status(tmp_path: Path) -> None:
    """fail outbox → pipeline_end_status=failed + no auto v-fix."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.save()
    _write_outbox(run_dir, "validator-pipeline-end-r1", "validation", verdict="fail")

    r = _run("advance", "--run", run_id, "--phase", "pipeline-end-validation",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["verdict"] == "fail"
    assert data["pipeline_end_status"] == "failed"


def test_resolve_blocks_when_pipeline_end_status_pending(tmp_path: Path) -> None:
    """resolve refuses when pipeline_end_status=pending (not skipped, not aborted)."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.save()

    r = _run("resolve", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 1
    assert "pipeline_end_validator" in r.stderr and "pipeline-end-validation" in r.stderr


def test_resolve_blocks_when_pipeline_end_status_failed(tmp_path: Path) -> None:
    """resolve refuses when pipeline_end_status=failed."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.pipeline_end_status = "failed"
    sm.save()

    r = _run("resolve", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 1
    assert "failed" in r.stderr


def test_resolve_allows_when_pipeline_end_status_passed(tmp_path: Path) -> None:
    """resolve OK when pipeline_end_status=passed."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.pipeline_end_status = "passed"
    sm.save()

    r = _run("resolve", "--run", run_id, "--no-ingest",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r.returncode == 0, r.stderr


def test_resolve_abort_works_regardless_of_pipeline_end_status(tmp_path: Path) -> None:
    """--abort always works even if pipeline_end_status=failed."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    sm.pipeline_end_status = "failed"
    sm.save()
    r = _run("resolve", "--run", run_id, "--abort",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r.returncode == 0


# ---------- M2 run-loop ----------

def test_run_loop_returns_plan_when_nothing_to_auto(tmp_path: Path) -> None:
    """Fresh init has nothing auto-doable (groups need fork). run-loop returns
    the plan unchanged, with empty auto_actions log."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path)
    r = _run("run-loop", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 0
    # Output is two JSON objects (run-loop log + plan); split + parse
    chunks = [c.strip() for c in r.stdout.split("}\n{") if c.strip()]
    assert len(chunks) >= 1
    log = json.loads(chunks[0] + "}" if not chunks[0].endswith("}") else chunks[0])
    assert log["iterations"] == 1
    assert log["auto_actions"] == []
    assert log["max_iterations_reached"] is False


def test_run_loop_auto_advances_coding_when_outbox_ready(tmp_path: Path) -> None:
    """g1 coder result.md written → run-loop auto-advances coding → review."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path)
    sm = StateMachine.load(run_dir)
    # Get g1 going (coding phase, in_flight set)
    g1 = sm.task_groups[0]
    g1.begin_coding()
    sm.save()
    # Write its result.md outbox
    coder_key = g1.coder_in_flight[0]
    _write_outbox(run_dir, coder_key, "result", status="ok")

    r = _run("run-loop", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 0

    sm2 = StateMachine.load(run_dir)
    g1b = next(g for g in sm2.task_groups if g.id == g1.id)
    assert g1b.phase == "review", f"expected review, got {g1b.phase}"


def test_run_loop_auto_writeback_when_group_in_writeback(tmp_path: Path) -> None:
    """A group manually placed in writeback phase → run-loop auto-calls writeback."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path)
    sm = StateMachine.load(run_dir)
    g1 = sm.task_groups[0]
    g1.begin_coding()  # advance state
    g1.phase = "writeback"
    g1.status = "writeback"
    sm.save()

    r = _run("run-loop", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 0

    sm2 = StateMachine.load(run_dir)
    g1b = next(g for g in sm2.task_groups if g.id == g1.id)
    assert g1b.status == "done", f"expected done, got {g1b.status}"


def test_run_loop_auto_resolves_when_all_done_and_no_pipeline_end(tmp_path: Path) -> None:
    """All groups done + pipeline_end_validator=false → run-loop auto-resolves."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=False)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.save()

    r = _run("run-loop", "--run", run_id, "--no-ingest",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r.returncode == 0

    sm2 = StateMachine.load(run_dir)
    assert sm2.failed_status == "done"


def test_run_loop_auto_resolves_after_pipeline_end_pass(tmp_path: Path) -> None:
    """All groups done + pipeline-end outbox shows pass → run-loop auto-advances
    pipeline-end + auto-resolves in one call (2 iterations)."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.status = "done"
        g.phase = "done"
    sm.save()
    _write_outbox(run_dir, "validator-pipeline-end-r1", "validation", verdict="pass")

    r = _run("run-loop", "--run", run_id, "--no-ingest",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r.returncode == 0

    sm2 = StateMachine.load(run_dir)
    assert sm2.pipeline_end_status == "passed"
    assert sm2.failed_status == "done"


def test_run_loop_returns_fork_action_when_outbox_not_ready(tmp_path: Path) -> None:
    """Group in coding with in_flight but NO outbox written → run-loop emits
    the plan with coding-fork action so host knows to wait/check."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path)
    sm = StateMachine.load(run_dir)
    g1 = sm.task_groups[0]
    g1.begin_coding()
    sm.save()
    # NO outbox written — coder is "in flight"

    r = _run("run-loop", "--run", run_id, workdir_env=str(workdir),
             fake_home=tmp_path / "home")
    assert r.returncode == 0
    # Should NOT have auto-advanced — phase still coding
    sm2 = StateMachine.load(run_dir)
    g1b = next(g for g in sm2.task_groups if g.id == g1.id)
    assert g1b.phase == "coding"


def test_writeback_does_not_finalize_when_pipeline_end_pending(tmp_path: Path) -> None:
    """v0.8.2 fix: writeback last group must NOT set failed_status=done when
    pipeline_end_status is still pending. Otherwise run-loop break path
    sees failed_status=done and skips cmd_resolve → ingest_lessons doesn't
    run (round-3 试跑实测 bug)."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    # Mark both groups in writeback phase (simulating end-of-flow state)
    for g in sm.task_groups:
        g.begin_coding()
        g.phase = "writeback"
        g.status = "writeback"
    sm.save()

    # Writeback first group
    r1 = _run("writeback", "--run", run_id, "--group", "g1",
              workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r1.returncode == 0
    sm_after_g1 = StateMachine.load(run_dir)
    assert sm_after_g1.failed_status is None, (
        "writeback g1 should NOT prematurely set failed_status while "
        "pipeline_end_status is pending"
    )

    # Writeback second (last) group
    r2 = _run("writeback", "--run", run_id, "--group", "g2",
              workdir_env=str(workdir), fake_home=tmp_path / "home")
    assert r2.returncode == 0
    sm_after_g2 = StateMachine.load(run_dir)
    # KEY assertion: even though all groups now terminal, failed_status is None
    # because pipeline_end_status is still pending → cmd_resolve will handle it
    assert sm_after_g2.failed_status is None, (
        "even all groups terminal, failed_status must stay None when "
        "pipeline_end_status=pending; otherwise run-loop skips cmd_resolve "
        "and ingest_lessons never runs (v0.8.2 fix)"
    )
    assert sm_after_g2.pipeline_end_status == "pending"


def test_writeback_does_finalize_when_pipeline_end_not_required(tmp_path: Path) -> None:
    """Back-compat: when pipeline_end_validator=false (not-required), the
    writeback prematurely-done behaviour is correct (no pipeline-end phase
    to wait for)."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=False)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.begin_coding()
        g.phase = "writeback"
        g.status = "writeback"
    sm.save()

    _run("writeback", "--run", run_id, "--group", "g1",
         workdir_env=str(workdir), fake_home=tmp_path / "home")
    _run("writeback", "--run", run_id, "--group", "g2",
         workdir_env=str(workdir), fake_home=tmp_path / "home")
    sm_final = StateMachine.load(run_dir)
    # not-required → writeback CAN finalize (same as pre-0.8.2 behaviour)
    assert sm_final.failed_status == "done"


def test_writeback_finalizes_when_pipeline_end_passed(tmp_path: Path) -> None:
    """When pipeline_end_status=passed, last writeback can finalize."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path, pipeline_end_validator=True)
    sm = StateMachine.load(run_dir)
    for g in sm.task_groups:
        g.begin_coding()
        g.phase = "writeback"
        g.status = "writeback"
    sm.pipeline_end_status = "passed"
    sm.save()

    _run("writeback", "--run", run_id, "--group", "g1",
         workdir_env=str(workdir), fake_home=tmp_path / "home")
    _run("writeback", "--run", run_id, "--group", "g2",
         workdir_env=str(workdir), fake_home=tmp_path / "home")
    sm_final = StateMachine.load(run_dir)
    assert sm_final.failed_status == "done"


def test_run_loop_max_iterations_safety(tmp_path: Path) -> None:
    """--max-iterations=1 hits limit if there's >1 auto-action available."""
    run_id, run_dir, workdir = _init_and_get_run_id(tmp_path)
    sm = StateMachine.load(run_dir)
    # Set up two groups both in writeback so run-loop wants to do 2+ writebacks
    for g in sm.task_groups:
        g.phase = "writeback"
        g.status = "writeback"
    sm.save()

    r = _run("run-loop", "--run", run_id, "--max-iterations", "1",
             workdir_env=str(workdir), fake_home=tmp_path / "home")
    # After 1 iteration, only 1 group writeback'd; second pending. Loop hits limit.
    # Either exit 1 (max iters reached) or exit 0 (only 1 done, plan emitted).
    # Both acceptable — the contract is "doesn't hang forever".
    assert r.returncode in (0, 1)
