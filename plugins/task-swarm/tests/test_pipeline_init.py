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
    assert len(state["groups"]) >= 1

def test_init_pipeline_then_plan_runs(tmp_path):
    work = tmp_path / "proj"; work.mkdir()
    yml = _write_yml(tmp_path)
    init = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work),
                           home=tmp_path / "_home").stdout)
    cp = _run("plan", "--run", init["run_id"], cwd=work, home=tmp_path / "_home")
    assert cp.returncode == 0, cp.stderr
    plan = json.loads(cp.stdout)
    assert plan["phase"] in ("coding", "init")
    assert plan.get("action") in ("coding-fork", None) or plan.get("fork") is not None

def test_neither_tasks_nor_pipeline_errors(tmp_path):
    cp = _run("init", "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1
    assert "tasks" in cp.stderr.lower() or "pipeline" in cp.stderr.lower()

def test_both_tasks_and_pipeline_errors(tmp_path):
    yml = _write_yml(tmp_path)
    (tmp_path / "t.md").write_text("## 阶段 1: A\n- [ ] 1.1 x @writes:a.py\n", encoding="utf-8")
    cp = _run("init", "--tasks", str(tmp_path / "t.md"), "--pipeline", str(yml),
              "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1
    assert "二选一" in cp.stderr or "both" in cp.stderr.lower()

def test_invalid_pipeline_schema_errors(tmp_path):
    bad = tmp_path / "bad.yml"; bad.write_text("version: 1\ntask_groups: []\n", encoding="utf-8")
    cp = _run("init", "--pipeline", str(bad), "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1 and "task_groups" in cp.stderr

def test_malformed_yaml_errors(tmp_path):
    bad = tmp_path / "bad.yml"; bad.write_text("task_groups:\n  - id: g1\n    review: {reviewer: true}\n", encoding="utf-8")
    cp = _run("init", "--pipeline", str(bad), "--workdir", str(tmp_path), home=tmp_path / "_home")
    assert cp.returncode == 1
    assert "flow map" in cp.stderr.lower() or "解析失败" in cp.stderr
