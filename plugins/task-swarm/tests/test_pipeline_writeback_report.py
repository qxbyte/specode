"""tests for pipeline-path writeback (finalize without markdown) + report command."""
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


_YML = ('version: 1\ntask_groups:\n  - id: g1\n    name: A\n    tasks:\n'
        '      - id: g1.1\n        title: alpha\n        writes: [src/a.py]\n')


def _drive_to_writeback(tmp_path, home, work):
    yml = tmp_path / "pipeline.yml"
    yml.write_text(_YML, encoding="utf-8")
    init = json.loads(_run("init", "--pipeline", str(yml), "--workdir", str(work), home=home).stdout)
    run_id = init["run_id"]
    run_dir = Path(init["run_dir"])
    _run("plan", "--run", run_id, cwd=work, home=home)
    _write_coder_result(run_dir, "coder-g1-s1.1-r1")
    _run("advance", "--run", run_id, "--group", "g1", "--phase", "coding", "--round", "1", cwd=work, home=home)
    _write_reviewer(run_dir, 1, with_p0=False)
    _run("advance", "--run", run_id, "--group", "g1", "--phase", "review", "--round", "1", cwd=work, home=home)
    _write_validator(run_dir, 1, 1, verdict="pass")
    _run("advance", "--run", run_id, "--group", "g1", "--phase", "validation", "--round", "1", cwd=work, home=home)
    return run_id, run_dir


def test_writeback_pipeline_finalizes_without_tasks_md(tmp_path):
    home = tmp_path / "_home"
    home.mkdir()
    work = tmp_path / "proj"
    work.mkdir()
    run_id, run_dir = _drive_to_writeback(tmp_path, home, work)
    cp = _run("writeback", "--run", run_id, "--group", "g1", cwd=work, home=home)
    assert cp.returncode == 0, cp.stderr
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["task_groups"][0]["status"] == "done"
    assert not (work / "tasks.md").exists()
    assert not (run_dir / "tasks.md").exists()


def test_report_renders_after_writeback(tmp_path):
    home = tmp_path / "_home"
    home.mkdir()
    work = tmp_path / "proj"
    work.mkdir()
    run_id, run_dir = _drive_to_writeback(tmp_path, home, work)
    _run("writeback", "--run", run_id, "--group", "1", cwd=work, home=home)
    cp = _run("report", "--run", run_id, cwd=work, home=home)
    assert cp.returncode == 0, cp.stderr
    out = cp.stdout
    assert "g1" in out and "A" in out
    assert "1.1" in out and "alpha" in out
    assert "src/a.py" in out
    assert "done" in out.lower() or "pass" in out.lower()


def test_report_to_file(tmp_path):
    home = tmp_path / "_home"
    home.mkdir()
    work = tmp_path / "proj"
    work.mkdir()
    run_id, run_dir = _drive_to_writeback(tmp_path, home, work)
    _run("writeback", "--run", run_id, "--group", "1", cwd=work, home=home)
    out_file = tmp_path / "report.md"
    cp = _run("report", "--run", run_id, "--out", str(out_file), cwd=work, home=home)
    assert cp.returncode == 0, cp.stderr
    assert out_file.exists() and "1.1" in out_file.read_text(encoding="utf-8")
