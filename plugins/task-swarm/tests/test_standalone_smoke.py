"""standalone smoke: task-swarm runs end-to-end with zero specode dependency,
and emitted messages carry no specode wording."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _run(*args, cwd=None, home=None):
    env = os.environ.copy()
    if home:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
    env.setdefault("PYTHONUTF8", "1")
    cmd = [sys.executable, str(SCRIPTS_DIR / "task_swarm.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=30,
                          cwd=str(cwd) if cwd else None)


_YML = ('version: 1\ntask_groups:\n  - id: g1\n    name: A\n    tasks:\n'
        '      - id: g1.1\n        title: alpha\n        writes: [src/a.py]\n')


def _write_coder_result(run_dir: Path, agent_key: str) -> None:
    outbox = run_dir / "agents" / agent_key / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    (outbox / "result.md").write_text(
        "# c\n## 上下文\n- x\n## 子任务状态\n- 1.1 t: done — f.py\n"
        "## 关键变更\n- a\n\nSTATUS: ok\n", encoding="utf-8")


def _write_reviewer(run_dir: Path, group: int) -> None:
    out = run_dir / "agents" / f"reviewer-g{group}-r1" / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    (out / "review.md").write_text(
        "# rev\n## 结论\napproved-with-comments\n\n## P0\n(none)\n\n"
        "## P1\n## P2\nSTATUS: ok\n", encoding="utf-8")


def _write_validator(run_dir: Path, group: int, round_: int) -> None:
    out = run_dir / "agents" / f"validator-g{group}-r{round_}" / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    (out / "validation.md").write_text(
        "# v\n## 判定\npass\n## 复现命令\n```bash\npytest\n```\n"
        "## 按子任务的验证结果\n- [x] 1.1 t: pass\n\nSTATUS: ok\n", encoding="utf-8")


def _drive_full(tmp_path, home, work):
    yml = tmp_path / "pipeline.yml"
    yml.write_text(_YML, encoding="utf-8")
    init = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work), home=home).stdout)
    run_id, run_dir = init["run_id"], Path(init["run_dir"])
    _run("plan", "--run", run_id, cwd=work, home=home)
    _write_coder_result(run_dir, "coder-g1-s1-r1")
    _run("advance", "--run", run_id, "--phase", "coding", "--round", "1", cwd=work, home=home)
    _write_reviewer(run_dir, 1)
    _run("advance", "--run", run_id, "--phase", "review", "--round", "1", cwd=work, home=home)
    _write_validator(run_dir, 1, 1)
    _run("advance", "--run", run_id, "--phase", "validation", "--round", "1", cwd=work, home=home)
    _run("writeback", "--run", run_id, "--group", "1", cwd=work, home=home)
    return run_id, run_dir


def test_full_chain_runs_without_specode(tmp_path):
    home = tmp_path / "_home"; home.mkdir()
    work = tmp_path / "proj"; work.mkdir()
    run_id, run_dir = _drive_full(tmp_path, home, work)
    # state 落盘在 workdir 下,与 specode 无关
    assert (work / ".task-swarm" / "runs").exists()
    rp = _run("resolve", "--run", run_id, cwd=work, home=home)
    assert rp.returncode == 0, rp.stderr
    assert json.loads(rp.stdout)["status"] == "done"
    rep = _run("report", "--run", run_id, cwd=work, home=home)
    assert rep.returncode == 0, rep.stderr
    assert "alpha" in rep.stdout and "src/a.py" in rep.stdout


def test_all_done_message_has_no_specode(tmp_path):
    home = tmp_path / "_home"; home.mkdir()
    work = tmp_path / "proj"; work.mkdir()
    run_id, run_dir = _drive_full(tmp_path, home, work)
    # 全组 done 后 plan 返回 all-done 提示
    plan = _run("plan", "--run", run_id, cwd=work, home=home)
    blob = plan.stdout
    for bad in ("spec-mode", "acceptance", "specode", "spec_session"):
        assert bad not in blob, f"all-done 提示泄漏 specode 词: {bad!r} in {blob!r}"


def test_heartbeat_hint_has_no_spec_lock(tmp_path):
    home = tmp_path / "_home"; home.mkdir()
    work = tmp_path / "proj"; work.mkdir()
    yml = tmp_path / "pipeline.yml"; yml.write_text(_YML, encoding="utf-8")
    run_id = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work), home=home).stdout)["run_id"]
    hb = _run("heartbeat", "--run", run_id, cwd=work, home=home)
    assert hb.returncode == 0, hb.stderr
    for bad in ("spec_session", "spec 锁", "保活"):
        assert bad not in hb.stdout, f"heartbeat 提示泄漏 specode 词: {bad!r}"


def test_planner_subagent_deleted(tmp_path):
    # 决策 A:主代理 inline 兼 planner,遗留 planner 子 agent 必须删除
    assert not (PLUGIN_DIR / "agents" / "task-swarm-planner.md").exists()


def test_skill_md_exists_and_specode_free(tmp_path):
    skill = PLUGIN_DIR / "skills" / "task-swarm" / "SKILL.md"
    assert skill.exists(), "task-swarm 必须有自己的 SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "name: task-swarm" in text
    assert "description:" in text
    for bad in ("spec_session", "read-session", "spec-mode", "acceptance phase", "/specode:"):
        assert bad not in text, f"SKILL.md 泄漏 specode 词: {bad!r}"


def test_command_is_standalone_first(tmp_path):
    cmd = (PLUGIN_DIR / "commands" / "task-swarm.md").read_text(encoding="utf-8")
    # 入口多态 + 无 specode 前置门
    assert "pipeline.yml" in cmd
    for bad in ("read-session", "/specode:task-swarm", "回到 spec-mode", "tasks-execution selector 选中"):
        assert bad not in cmd, f"command 仍含 specode 耦合: {bad!r}"


def test_references_specode_free(tmp_path):
    ref = (PLUGIN_DIR / "skills" / "task-swarm" / "references" / "task-swarm.md").read_text(encoding="utf-8")
    for bad in ("/specode:task-swarm", "回到 spec-mode acceptance phase", "保活 spec 锁"):
        assert bad not in ref, f"references/task-swarm.md 仍含 specode 耦合: {bad!r}"
