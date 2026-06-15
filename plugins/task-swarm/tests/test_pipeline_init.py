import json, os, subprocess, sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

def _run(*args, cwd=None, home=None):
    env = os.environ.copy()
    if home:
        env["HOME"] = str(home); env["USERPROFILE"] = str(home)
    env.setdefault("PYTHONUTF8", "1")
    cmd = [sys.executable, str(SCRIPTS_DIR / "task_swarm.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=30,
                          cwd=str(cwd) if cwd else None)

_YML = ('version: 1\nrun:\n  max_parallel: 4\ntask_groups:\n'
        '  - id: g1\n    name: A\n    tasks:\n      - id: g1.1\n        title: alpha\n'
        '        writes: [src/a.py]\n        requirements: ["1.1"]\n')

def _write_yml(d: Path) -> Path:
    p = d / "pipeline.yml"; p.write_text(_YML, encoding="utf-8"); return p

def test_init_pipeline_builds_state(tmp_path):
    work = tmp_path / "proj"; work.mkdir()
    yml = _write_yml(tmp_path)
    cp = _run("init", "--pipeline", str(yml), "--workdir", str(work), home=tmp_path / "_home")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    run_dir = Path(out["run_dir"])
    assert (run_dir / "state.json").exists()
    assert (run_dir / "pipeline.yml").exists()
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["pipeline_path"].endswith("pipeline.yml")
    assert len(state["task_groups"]) >= 1

def test_init_pipeline_then_plan_runs(tmp_path):
    work = tmp_path / "proj"; work.mkdir()
    yml = _write_yml(tmp_path)
    init = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work),
                           home=tmp_path / "_home").stdout)
    cp = _run("plan", "--run", init["run_id"], cwd=work, home=tmp_path / "_home")
    assert cp.returncode == 0, cp.stderr
    plan = json.loads(cp.stdout)
    # M3: plan 返回 {schedule, actions:[...]}；自动 begin_coding g1 → coding-fork。
    actions = plan["actions"]
    assert len(actions) >= 1
    a0 = actions[0]
    assert a0["phase"] in ("coding", "init")
    assert a0.get("action") == "coding-fork"
    assert a0.get("fork")

def test_neither_tasks_nor_pipeline_errors(tmp_path):
    cp = _run("init", "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1
    assert "tasks" in cp.stderr.lower() or "pipeline" in cp.stderr.lower()

def test_invalid_pipeline_schema_errors(tmp_path):
    bad = tmp_path / "bad.yml"; bad.write_text("version: 1\ntask_groups: []\n", encoding="utf-8")
    cp = _run("init", "--pipeline", str(bad), "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1 and "task_groups" in cp.stderr

def test_malformed_yaml_errors(tmp_path):
    bad = tmp_path / "bad.yml"; bad.write_text("task_groups:\n  - id: g1\n    review: {reviewer: true}\n", encoding="utf-8")
    cp = _run("init", "--pipeline", str(bad), "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1
    assert "flow map" in cp.stderr.lower() or "解析失败" in cp.stderr


# -------------------------------------------------------------------------
# M3: 跨组并发调度（cli 层回归）
# -------------------------------------------------------------------------

_YML_MULTI = (
    'version: 1\ntask_groups:\n'
    '  - id: g1\n    name: A\n    tasks:\n      - id: g1.1\n        title: a\n        writes: [src/a.py]\n'
    '  - id: g2\n    name: B\n    tasks:\n      - id: g2.1\n        title: b\n        writes: [src/b.py]\n'
    '  - id: g3\n    name: C\n    needs: [g1]\n    tasks:\n      - id: g3.1\n        title: c\n        writes: [src/c.py]\n'
)


def test_plan_concurrent_independent_groups_and_needs_blocking(tmp_path):
    work = tmp_path / "proj"; work.mkdir()
    yml = tmp_path / "p.yml"; yml.write_text(_YML_MULTI, encoding="utf-8")
    init = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work),
                           home=tmp_path / "_home").stdout)
    plan = json.loads(_run("plan", "--run", init["run_id"], cwd=work,
                           home=tmp_path / "_home").stdout)
    # g1 + g2（writes 不相交、无 needs）→ 同一 plan 并发启动
    started = {a["group"] for a in plan["actions"]}
    assert started == {"g1", "g2"}, f"期望 g1,g2 并发启动, 实际 {started}"
    assert set(plan["schedule"]["running"]) == {"g1", "g2"}
    # g3 needs g1 → blocked
    assert any(b["id"] == "g3" for b in plan["schedule"]["blocked"])


_YML_CONFLICT = (
    'version: 1\ntask_groups:\n'
    '  - id: g1\n    name: A\n    tasks:\n      - id: g1.1\n        title: a\n        writes: [src/shared.py]\n'
    '  - id: g2\n    name: B\n    tasks:\n      - id: g2.1\n        title: b\n        writes: [src/shared.py]\n'
)


def test_plan_writes_conflict_serializes(tmp_path):
    work = tmp_path / "proj"; work.mkdir()
    yml = tmp_path / "c.yml"; yml.write_text(_YML_CONFLICT, encoding="utf-8")
    init = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work),
                           home=tmp_path / "_home").stdout)
    plan = json.loads(_run("plan", "--run", init["run_id"], cwd=work,
                           home=tmp_path / "_home").stdout)
    # g1,g2 写同一文件 → 只启动一个，另一个 blocked(conflict)
    started = {a["group"] for a in plan["actions"]}
    assert len(started) == 1, f"writes 冲突应只启动一个, 实际 {started}"
    assert any("conflict" in b["reason"] for b in plan["schedule"]["blocked"])
