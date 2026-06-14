"""tests for task_swarm.py — CLI 子命令端到端。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def run_swarm(tmp_path, monkeypatch):
    """运行 task_swarm.py CLI，cwd 设到 tmp_path 让 .task-swarm 目录可解析。"""
    monkeypatch.chdir(tmp_path)
    # 与 conftest.fake_home 一致：HOME 也指向 tmp 避免污染
    monkeypatch.setenv("HOME", str(tmp_path / "_home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "_home"))

    def _run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = str(tmp_path / "_home")
        env["USERPROFILE"] = str(tmp_path / "_home")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        cmd = [sys.executable, str(SCRIPTS_DIR / "task_swarm.py"), *args]
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              input=stdin, env=env, timeout=30, cwd=str(tmp_path))
    return _run


def _write_tasks_md(tmp_path: Path, num_stages: int = 2) -> Path:
    p = tmp_path / "tasks.md"
    lines = []
    for i in range(1, num_stages + 1):
        lines.append(f"## 阶段 {i}: 阶段 {i}")
        lines.append(f"- [ ] {i}.1 任务 @writes:src/f{i}.py _需求：{i}.1_")
        if i > 1:
            lines.append(f"- [ ] {i}.2 任务2 @writes:src/g{i}.py @depends-on:{i-1} _需求：{i}.2_")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _write_coder_result(run_dir: Path, agent_key: str, status: str = "ok") -> None:
    outbox = run_dir / "agents" / agent_key / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    (outbox / "result.md").write_text(
        "# c\n## 上下文\n- x\n## 子任务状态\n- 1.1 t: done — f.py\n## 关键变更\n- a\n\n"
        f"STATUS: {status}\n",
        encoding="utf-8",
    )


def _write_reviewer(run_dir: Path, group: int, with_p0: bool = True) -> None:
    out = run_dir / "agents" / f"reviewer-g{group}-r1" / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    p0_section = ("## P0\n- src/f1.py:5 [req:1.1] — issue\n\n"
                  if with_p0 else "## P0\n(none)\n\n")
    (out / "review.md").write_text(
        "# rev\n## 结论\napproved-with-comments\n\n"
        + p0_section
        + "## P1\n## P2\nSTATUS: ok\n",
        encoding="utf-8",
    )


def _write_validator(run_dir: Path, group: int, round_: int, verdict: str = "pass",
                     sig_marker: str = "default") -> None:
    out = run_dir / "agents" / f"validator-g{group}-r{round_}" / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    if verdict == "pass":
        body = ("# v\n## 判定\npass\n## 复现命令\n```bash\npytest\n```\n"
                "## 按子任务的验证结果\n- [x] 1.1 t: pass\n\nSTATUS: ok\n")
    else:
        body = ("# v\n## 判定\nfail\n## 复现命令\n```bash\npytest\n```\n"
                "## 按子任务的验证结果\n- [ ] 1.1 t: fail\n"
                f"## 失败现场\n```\nFAILED tests/t.py::test_{sig_marker}\nAssertionError: x\n```\n"
                "## 给 coder 的修复指引\n### 修复 1\n- 文件: src/f1.py\n- 位置: x\n"
                "- 问题: y\n- 建议: z\n\nSTATUS: ok\n")
    (out / "validation.md").write_text(body, encoding="utf-8")


# -------------------------------------------------------------------------
# 测试
# -------------------------------------------------------------------------

def test_init_creates_state_and_groups(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=2)
    cp = run_swarm("init", "--tasks", str(p))
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert "run_id" in out
    assert len(out["groups"]) >= 1
    run_dir = Path(out["run_dir"])
    assert (run_dir / "state.json").exists()


def test_init_with_nonexistent_tasks_exits_1(tmp_path, run_swarm):
    cp = run_swarm("init", "--tasks", str(tmp_path / "no.md"))
    assert cp.returncode == 1


def test_init_empty_tasks_md_exits_1(tmp_path, run_swarm):
    p = tmp_path / "tasks.md"
    p.write_text("# nothing\n", encoding="utf-8")
    cp = run_swarm("init", "--tasks", str(p))
    assert cp.returncode == 1


def test_plan_initial_returns_coding_fork(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    cp = run_swarm("plan", "--run", init["run_id"])
    assert cp.returncode == 0
    plan = json.loads(cp.stdout)
    assert plan["phase"] == "coding"
    assert plan["action"] == "coding-fork"
    assert plan["fork"]


def test_status_reports_phase(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    cp = run_swarm("status", "--run", init["run_id"])
    assert cp.returncode == 0
    st = json.loads(cp.stdout)
    assert st["run_id"] == init["run_id"]
    assert st["phase"] in ("init", "coding")


def test_advance_coding_then_review_fork(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_dir = Path(init["run_dir"])
    # plan to materialize prompts + transition to coding
    run_swarm("plan", "--run", init["run_id"])
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    cp = run_swarm("advance", "--run", init["run_id"], "--phase", "coding", "--round", "1")
    assert cp.returncode == 0
    out = json.loads(cp.stdout)
    assert out["ok"]
    assert out["plan"]["action"] == "review-fork"


def test_full_cycle_no_p0_pass(tmp_path, run_swarm):
    """coding → review (no P0) → validation (pass) → writeback"""
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    _write_validator(run_dir, 1, 1, verdict="pass")
    cp = run_swarm("advance", "--run", run_id, "--phase", "validation", "--round", "1")
    out = json.loads(cp.stdout)
    assert out["plan"]["action"] == "writeback"
    cp = run_swarm("writeback", "--run", run_id, "--group", "1")
    assert cp.returncode == 0, cp.stderr
    text = p.read_text(encoding="utf-8")
    assert "- [x] 1.1" in text


def test_full_cycle_with_p0_fix(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=True)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    # p0-fix coder
    _write_coder_result(run_dir, "coder-p0fix-g1-r1-f0")
    cp = run_swarm("advance", "--run", run_id, "--phase", "p0-fix", "--round", "1")
    out = json.loads(cp.stdout)
    assert out["plan"]["phase"] == "validation"


def test_validation_fail_triggers_v_fix(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    _write_validator(run_dir, 1, 1, verdict="fail", sig_marker="first")
    cp = run_swarm("advance", "--run", run_id, "--phase", "validation", "--round", "1")
    out = json.loads(cp.stdout)
    assert out["plan"]["phase"] == "v-fix"


def test_deadloop_after_3_identical_fails(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    # 3 同样的 fail
    for r in range(1, 4):
        _write_validator(run_dir, 1, r, verdict="fail", sig_marker="same")
        cp = run_swarm("advance", "--run", run_id, "--phase", "validation", "--round", str(r))
        out = json.loads(cp.stdout)
        if r < 3:
            # v-fix coder 返回
            v_round = r + 1
            files = ["src/f1.py"]
            for i, _f in enumerate(files):
                key = f"coder-vfix-g1-r{v_round}-f{i}"
                _write_coder_result(run_dir, key)
            run_swarm("advance", "--run", run_id, "--phase", "v-fix", "--round", str(v_round))
    assert "deadloop" in out.get("next", "") or out.get("deadloop") is True


def test_writeback_invalid_group_returns_1(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    cp = run_swarm("writeback", "--run", init["run_id"], "--group", "99")
    assert cp.returncode == 1


def test_heartbeat_updates_state(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    cp = run_swarm("heartbeat", "--run", init["run_id"])
    assert cp.returncode == 0
    out = json.loads(cp.stdout)
    assert out["run_id"] == init["run_id"]


def test_resolve_abort_sets_status(tmp_path, run_swarm):
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    cp = run_swarm("resolve", "--run", init["run_id"], "--abort")
    assert cp.returncode == 0
    out = json.loads(cp.stdout)
    assert out["status"] == "aborted"


def test_init_resolve_never_touch_host_session(tmp_path, run_swarm, monkeypatch):
    """0.10.x 解耦:task-swarm 不再读/写 ~/.specode/sessions/<id>.json。

    --session 仅作为日志维度透传,init/resolve 都不得碰宿主 session 文件
    （task_swarm_run_id 字段彻底移除）。"""
    monkeypatch.setenv("HOME", str(tmp_path / "_home"))
    sid = "test-sess-123"
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p), "--session", sid).stdout)
    # init 不应创建任何宿主 session 文件
    sess_file = tmp_path / "_home" / ".specode" / "sessions" / f"{sid}.json"
    assert not sess_file.exists()
    # session_id 仍被记录进 state.json
    state = json.loads((Path(init["run_dir"]) / "state.json").read_text(encoding="utf-8"))
    assert state["session_id"] == sid
    # resolve 同样不碰宿主 session
    run_swarm("resolve", "--run", init["run_id"])
    assert not (tmp_path / "_home" / ".specode").exists()


def test_v_fix_prompt_files_match_state_in_flight(tmp_path, run_swarm):
    """Regression: validation fail → begin_v_fix 之后，磁盘上 agents/<key>/task.md
    的 round 号必须与 state.json 的 vfix_in_flight 一致。

    历史 bug：_materialize_prompts_v_fix 用 round_=sm.round+1，但 begin_v_fix 已经
    把 sm.round 自增过了，且 vfix_in_flight 用的就是 sm.round 命名。结果磁盘
    task.md 比 in_flight 多一个 round 号（state 是 r2、磁盘是 r3）。后续 advance
    找不到 r2 的 result.md，永远报 '产物文件不存在'。
    """
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])

    # 走完 coding + review（无 P0）→ 直接进 validation
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")

    # validation round 1 fail → 触发 begin_v_fix + _materialize_prompts_v_fix
    _write_validator(run_dir, 1, 1, verdict="fail", sig_marker="x")
    run_swarm("advance", "--run", run_id, "--phase", "validation", "--round", "1")

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "v-fix"
    assert state["round"] == 2
    in_flight = state["vfix_in_flight"]
    assert in_flight, "begin_v_fix 之后 vfix_in_flight 应非空"

    # 关键断言：每个 in_flight key 对应的 agents/<key>/task.md 必须存在
    agents_dir = run_dir / "agents"
    existing = {p.name for p in agents_dir.iterdir() if p.is_dir()}
    for key in in_flight:
        task_md = agents_dir / key / "task.md"
        assert task_md.exists(), (
            f"in_flight 含 {key!r} 但磁盘 task.md 不存在: {task_md}\n"
            f"agents 目录实际成员: {sorted(existing)}\n"
            f"（典型 r/r+1 漂移 bug：state 是 r{state['round']}、"
            f"磁盘可能是 r{state['round']+1}）"
        )


def test_coder_prompt_includes_project_root_from_flag(tmp_path, run_swarm):
    project_root = tmp_path / "my-app"
    project_root.mkdir()
    tasks_md = tmp_path / "tasks.md"
    tasks_md.write_text(
        "## 阶段 1: 阶段 1\n"
        "- [ ] 1.1 任务 @writes:src/f1.py _需求：1.1_\n",
        encoding="utf-8",
    )
    init = json.loads(run_swarm("init", "--tasks", str(tasks_md),
                                "--workdir", str(tmp_path),
                                "--project-root", str(project_root)).stdout)
    run_swarm("plan", "--run", init["run_id"])
    run_dir = Path(init["run_dir"])
    task_md = next(run_dir.glob("agents/coder-*/task.md"))
    assert str(project_root) in task_md.read_text(encoding="utf-8")


def test_writeback_handles_multi_line_reproduce_cmd(tmp_path, run_swarm):
    """0.10.21+ 回归：validator pass 的 reproduce_cmd 含多行（cd ... + node -e "..."）
    不应让 writeback 报"line-safe 越界"。

    历史 bug（login-page 现场）：_format_findings_block 把 multi-line cmd 拼成
    inline string，写入 tasks.md 后被 splitlines 拆出非 `>` 前缀的行，
    _verify_line_safe 报"writeback 越界：line N 原 '## 阶段 5:' 新 '# 验证 ...'"。
    """
    # 自造 tasks.md（2 阶段，触发 stage 间插入注释）
    p = tmp_path / "tasks.md"
    p.write_text(
        "## 阶段 1: 阶段 1\n"
        "- [ ] 1.1 任务 @writes:src/f1.py _需求：1.1_\n"
        "\n"
        "## 阶段 2: 阶段 2\n"
        "- [ ] 2.1 任务2 @writes:src/g2.py @depends-on:1 _需求：2.1_\n",
        encoding="utf-8",
    )
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    # 手工写 validator validation.md，含多行 reproduce_cmd
    out_dir = run_dir / "agents" / "validator-g1-r1" / "outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    multi_line_cmd_body = (
        "# v\n"
        "## 判定\npass\n"
        "## 复现命令\n"
        "```bash\n"
        "cd /tmp/project\n"
        "\n"
        "# 验证 P0 修复\n"
        "node -e \"console.log('ok')\"\n"
        "```\n"
        "## 按子任务的验证结果\n- [x] 1.1: pass\n\n"
        "STATUS: ok\n"
    )
    (out_dir / "validation.md").write_text(multi_line_cmd_body, encoding="utf-8")
    run_swarm("advance", "--run", run_id, "--phase", "validation", "--round", "1")
    # writeback 必须成功（不报越界）
    cp = run_swarm("writeback", "--run", run_id, "--group", "1")
    assert cp.returncode == 0, (
        f"writeback 失败：stderr={cp.stderr}\nstdout={cp.stdout}"
    )
    tasks_after = p.read_text(encoding="utf-8")
    # 多行命令应该以 ``` fenced 块的形式出现，每行带 >
    assert "validator g1-r1 pass，复现命令" in tasks_after
    assert "> ```" in tasks_after
    assert "> cd /tmp/project" in tasks_after
    assert "> # 验证 P0 修复" in tasks_after


def test_init_skip_validator_flag_persists_to_state(tmp_path, run_swarm):
    """0.10.20+：init --skip-validator 把 skip_validator=true 写入 state.json。"""
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(
        run_swarm("init", "--tasks", str(p), "--skip-validator").stdout
    )
    run_dir = Path(init["run_dir"])
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["skip_validator"] is True


def test_init_without_flag_defaults_to_full_mode(tmp_path, run_swarm):
    """0.10.20+：默认 skip_validator=false（兼容老行为）。"""
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(run_swarm("init", "--tasks", str(p)).stdout)
    run_dir = Path(init["run_dir"])
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["skip_validator"] is False


def test_skip_validator_review_no_p0_skips_validation(tmp_path, run_swarm):
    """0.10.20+：skip_validator=true + review 无 P0 → advance review 后直接进 writeback，
    跳过 validation。"""
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(
        run_swarm("init", "--tasks", str(p), "--skip-validator").stdout
    )
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    cp = run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["phase"] == "writeback", (
        f"skip_validator 模式无 P0 → 应直接进 writeback，实际 phase={out['phase']}"
    )


def test_skip_validator_p0_fix_done_skips_validation(tmp_path, run_swarm):
    """0.10.20+：skip_validator=true + p0-fix 完成 → 直接进 writeback。"""
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(
        run_swarm("init", "--tasks", str(p), "--skip-validator").stdout
    )
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=True)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    # p0-fix coder 返回
    _write_coder_result(run_dir, "coder-p0fix-g1-r1-f0")
    cp = run_swarm("advance", "--run", run_id, "--phase", "p0-fix", "--round", "1")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["phase"] == "writeback", (
        f"skip_validator 模式 p0-fix 完 → 应直接进 writeback，实际 phase={out['phase']}"
    )


def test_skip_validator_writeback_writes_skipped_note(tmp_path, run_swarm):
    """0.10.20+：skip_validator 模式 writeback 时 tasks.md 注释块写
    "⏭️ validator 已跳过（人工验收模式）"。"""
    p = _write_tasks_md(tmp_path, num_stages=1)
    init = json.loads(
        run_swarm("init", "--tasks", str(p), "--skip-validator").stdout
    )
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    run_swarm("plan", "--run", run_id)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    run_swarm("advance", "--run", run_id, "--phase", "coding", "--round", "1")
    _write_reviewer(run_dir, 1, with_p0=False)
    run_swarm("advance", "--run", run_id, "--phase", "review", "--round", "1")
    cp = run_swarm("writeback", "--run", run_id, "--group", "1")
    assert cp.returncode == 0, cp.stderr
    tasks_after = p.read_text(encoding="utf-8")
    assert "validator 已跳过" in tasks_after
    assert "人工验收模式" in tasks_after
    # 不应当出现 "✅ validator g1-rN pass"
    assert "✅ validator" not in tasks_after
