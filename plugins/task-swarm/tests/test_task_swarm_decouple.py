"""解耦回归:状态根 = workdir、project_root/spec_id 由 flag 驱动、无 .config.json 依赖。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


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


def _tasks_md(d: Path) -> Path:
    """M3：单组 pipeline.yml（沿用旧 helper 名以减少改动面）。"""
    p = d / "pipeline.yml"
    p.write_text(
        "version: 1\ntask_groups:\n  - id: g1\n    name: A\n    tasks:\n"
        "      - id: g1.1\n        title: 任务\n        writes: [src/f1.py]\n"
        '        requirements: ["1.1"]\n',
        encoding="utf-8",
    )
    return p


def test_init_uses_explicit_workdir_for_state_root(tmp_path):
    work = tmp_path / "proj"
    work.mkdir()
    tasks = _tasks_md(tmp_path)            # tasks.md elsewhere; workdir separate
    cp = _run("init", "--pipeline", str(tasks), "--workdir", str(work),
              home=tmp_path / "_home")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    run_dir = Path(out["run_dir"])
    assert str(run_dir).startswith(str(work / ".task-swarm" / "runs"))
    assert (run_dir / "state.json").exists()


def test_init_stores_project_root_from_flag(tmp_path):
    work = tmp_path / "proj"
    work.mkdir()
    tasks = _tasks_md(tmp_path)
    pr = tmp_path / "app"
    pr.mkdir()
    cp = _run("init", "--pipeline", str(tasks), "--workdir", str(work),
              "--project-root", str(pr), home=tmp_path / "_home")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    state = json.loads((Path(out["run_dir"]) / "state.json").read_text(encoding="utf-8"))
    assert state["project_root"] == str(pr)
    assert state["workdir"] == str(work)


def _coder_task_md(run_dir: Path) -> Path:
    matches = sorted((run_dir / "agents").glob("coder-*/task.md"))
    assert matches, f"未找到 coder task.md，run_dir={run_dir}"
    return matches[0]


def test_coder_prompt_omits_spec_dir_when_absent(tmp_path):
    work = tmp_path / "proj"
    work.mkdir()
    tasks = _tasks_md(tmp_path)
    home = tmp_path / "_home"
    cp = _run("init", "--pipeline", str(tasks), "--workdir", str(work), home=home)
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    run_dir = Path(out["run_dir"])
    cp2 = _run("plan", "--run", out["run_id"], cwd=work, home=home)
    assert cp2.returncode == 0, cp2.stderr
    text = _coder_task_md(run_dir).read_text(encoding="utf-8")
    # 无 spec_dir：既不出现空 spec_dir: 行，也不出现「严禁写到 spec_dir/」误导文案
    assert "spec_dir" not in text, text
    assert "严禁" in text  # 「严禁评价自己产物 / 严禁改 @writes 之外」是合法协议行，应保留
    assert "写到 `spec_dir/`" not in text, text


def test_coder_prompt_includes_spec_dir_when_provided(tmp_path):
    work = tmp_path / "proj"
    work.mkdir()
    spec_dir = tmp_path / "spec-docs"
    spec_dir.mkdir()
    tasks = _tasks_md(tmp_path)
    home = tmp_path / "_home"
    cp = _run("init", "--pipeline", str(tasks), "--workdir", str(work),
              "--spec-dir", str(spec_dir), home=home)
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    run_dir = Path(out["run_dir"])
    cp2 = _run("plan", "--run", out["run_id"], cwd=work, home=home)
    assert cp2.returncode == 0, cp2.stderr
    text = _coder_task_md(run_dir).read_text(encoding="utf-8")
    assert str(spec_dir) in text, text


def test_plan_finds_run_in_workdir_without_sessions(tmp_path):
    work = tmp_path / "proj"
    work.mkdir()
    tasks = _tasks_md(tmp_path)
    init = json.loads(_run("init", "--pipeline", str(tasks), "--workdir", str(work),
                           home=tmp_path / "_home").stdout)
    run_id = init["run_id"]
    cp = _run("plan", "--run", run_id, cwd=work, home=tmp_path / "_home")
    assert cp.returncode == 0, cp.stderr
    plan = json.loads(cp.stdout)
    assert plan["actions"][0]["phase"] in ("coding", "init")


def test_full_cycle_creates_no_specode_dir(tmp_path):
    home = tmp_path / "_home"
    home.mkdir()
    work = tmp_path / "proj"
    work.mkdir()
    tasks = _tasks_md(tmp_path)
    init = json.loads(_run("init", "--pipeline", str(tasks), "--workdir", str(work),
                           "--session", "sid-xyz", home=home).stdout)
    run_id = init["run_id"]
    _run("plan", "--run", run_id, cwd=work, home=home)
    _run("resolve", "--run", run_id, "--abort", cwd=work, home=home)
    assert not (home / ".specode").exists()
