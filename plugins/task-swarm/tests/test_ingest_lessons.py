# -*- coding: utf-8 -*-
"""Tests for task_swarm._ingest_lessons (P2-1).

Builds a minimal StateMachine + an outbox tree on disk, then verifies
the resulting case/pitfall yml under <project_root>/.ai-memory/."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._ingest_lessons import ingest_lessons  # noqa: E402
from task_swarm._state import GroupState, StateMachine  # noqa: E402


def _mk_state(workdir: Path, *, project_root: Path | None = None,
              spec_id: str | None = "REQ-001") -> StateMachine:
    run_dir = workdir / ".task-swarm" / "runs" / "r1"
    (run_dir / "agents").mkdir(parents=True, exist_ok=True)
    gs = GroupState(
        id="g1",
        name="checkout pricing pipeline",
        items=[{"number": 1, "title": "implement pricing", "writes": ["src/pricing.py"]}],
        status="done",
        phase="done",
    )
    sm = StateMachine(
        run_id="r1",
        tasks_md="",
        run_dir=str(run_dir),
        workdir=str(workdir),
        project_root=str(project_root) if project_root else None,
        spec_id=spec_id,
        spec_dir="SpecIn/specs/REQ-001",
        task_groups=[gs],
        failed_status="done",
        completed_at="2026-06-26T00:00:00Z",
    )
    return sm


def _write_outbox(run_dir: Path, agent_key: str, filename: str, content: str) -> Path:
    p = run_dir / "agents" / agent_key / "outbox" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _read_yml(path: Path) -> dict:
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        return json.loads(path.read_text(encoding="utf-8"))


_VALID_REVIEW = """\
## 结论

needs-changes

## P0（带证据的阻断项）

- amount 校验缺失，会导致 NPE [req:1.2] (src/pricing.py)

## P1

- 缺少边界测试

## P2

- 命名风格不统一

## 给使用者的提示

amount validation gap.

STATUS: ok
"""

_VALID_VALIDATION_PASS = """\
## 判定

pass

## 复现命令

```bash
pytest
```

## 按子任务的验证结果

- [x] 1.1 implement pricing：pass

STATUS: ok
"""

_VALID_VALIDATION_FAIL = """\
## 判定

fail

## 复现命令

```bash
pytest tests/test_pricing.py -k null_amount
```

## 按子任务的验证结果

- [x] 1.1 implement pricing：fail

## 失败现场（fail 时必填）

```
FAILED tests/test_pricing.py::test_null_amount
AssertionError: BigDecimal.add NPE on null amount
```

## 给 coder 的修复指引（fail 时必填，按文件分组）

### 修复 1 — handle null amount

- 文件: src/pricing.py
- 位置: calculate_price line 42
- 问题: NPE when amount is None
- 建议: wrap with Optional.ofNullable(amount).orElse(BigDecimal.ZERO)

STATUS: ok
"""

_CODER_RESULT = """\
## 关键变更

- introduced calculate_price() with null-guard
- added unit test for null amount

## 子任务状态

- [x] 1.1 implement pricing：done

## 给下游 reviewer 的提示

- watch the BigDecimal null branch

STATUS: ok
"""


class IngestLessonsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ts-ingest-"))
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.sm = _mk_state(self.project, project_root=self.project)
        self.run_dir = Path(self.sm.run_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- skip paths ----------

    def test_skipped_when_no_project_root(self) -> None:
        self.sm.project_root = None
        self.sm.workdir = None
        result = ingest_lessons(self.sm)
        self.assertEqual(result["skipped"], "no project_root")
        self.assertEqual(result["cases"], [])
        self.assertEqual(result["pitfalls"], [])

    def test_creates_knowledge_dir_when_missing(self) -> None:
        # No agents/outbox files seeded → ingest just creates empty case yml.
        result = ingest_lessons(self.sm)
        self.assertIsNone(result["skipped"])
        self.assertTrue((self.project / ".ai-memory" / "knowledge" / "cases").is_dir())
        self.assertTrue((self.project / ".ai-memory" / "knowledge" / "pitfalls").is_dir())

    # ---------- case ----------

    def test_case_written_with_metadata(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        _write_outbox(self.run_dir, "reviewer-g1-r1", "review.md", _VALID_REVIEW)
        result = ingest_lessons(self.sm)
        self.assertEqual(len(result["cases"]), 1)
        case_path = Path(result["cases"][0])
        case = _read_yml(case_path)
        self.assertEqual(case["knowledge_id"], "case-REQ-001-g1")
        self.assertEqual(case["type"], "case")
        self.assertEqual(case["spec_id"], "REQ-001")
        self.assertEqual(case["group_id"], "g1")
        self.assertEqual(case["title"], "checkout pricing pipeline")
        self.assertIn("src/pricing.py", case["changed_files"])
        # key_changes go into implementation_summary; reviewer hints into key_decisions.
        self.assertIn("null-guard", case["implementation_summary"])
        self.assertTrue(
            any("BigDecimal null branch" in d.get("decision", "") for d in case["key_decisions"]),
            f"expected reviewer hint in key_decisions, got {case['key_decisions']}",
        )

    def test_case_acceptance_passed_when_validator_passes(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        self.sm.task_groups[0].validator_history = [{"round": 1, "verdict": "pass"}]
        _write_outbox(self.run_dir, "validator-g1-r1", "validation.md", _VALID_VALIDATION_PASS)
        result = ingest_lessons(self.sm)
        case = _read_yml(Path(result["cases"][0]))
        self.assertEqual(case["acceptance_status"], "passed")
        self.assertEqual(case["confidence"], "high")

    def test_case_review_findings_carry_severity(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        _write_outbox(self.run_dir, "reviewer-g1-r1", "review.md", _VALID_REVIEW)
        result = ingest_lessons(self.sm)
        case = _read_yml(Path(result["cases"][0]))
        self.assertTrue(case["review_findings"])
        self.assertEqual(case["review_findings"][0]["severity"], "p0")

    def test_no_case_for_unfinished_group(self) -> None:
        self.sm.task_groups[0].status = "coding"
        result = ingest_lessons(self.sm)
        self.assertEqual(result["cases"], [])

    # ---------- pitfall ----------

    def test_pitfall_written_for_validator_fail(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        self.sm.task_groups[0].validator_history = [
            {"round": 1, "verdict": "fail"},
            {"round": 2, "verdict": "pass"},
        ]
        _write_outbox(self.run_dir, "validator-g1-r1", "validation.md", _VALID_VALIDATION_FAIL)
        _write_outbox(self.run_dir, "validator-g1-r2", "validation.md", _VALID_VALIDATION_PASS)
        result = ingest_lessons(self.sm)
        self.assertEqual(len(result["pitfalls"]), 1)
        pit = _read_yml(Path(result["pitfalls"][0]))
        self.assertEqual(pit["type"], "pitfall")
        self.assertEqual(pit["first_seen_in"], "REQ-001")
        self.assertIn("BigDecimal.add NPE", pit["symptom"])
        self.assertIn("src/pricing.py", pit["affects"])
        self.assertTrue(
            any("Optional.ofNullable" in fix for fix in pit["fix"]),
            f"expected Optional.ofNullable suggestion, got {pit['fix']}",
        )

    def test_pitfall_merge_appends_seen_again_in(self) -> None:
        # Same signature, different spec — second ingest must append the new
        # spec_id to seen_again_in rather than overwriting first_seen_in.
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        self.sm.task_groups[0].validator_history = [{"round": 1, "verdict": "fail"}]
        _write_outbox(self.run_dir, "validator-g1-r1", "validation.md", _VALID_VALIDATION_FAIL)
        ingest_lessons(self.sm)

        # Now pretend a different spec sees the same failure.
        self.sm.spec_id = "REQ-002"
        # spec ingest also writes a new case file for REQ-002/g1.
        result2 = ingest_lessons(self.sm)
        pit_path = next(p for p in [Path(p) for p in result2["pitfalls"]])
        pit = _read_yml(pit_path)
        self.assertEqual(pit["first_seen_in"], "REQ-001")
        self.assertEqual(pit["seen_again_in"], ["REQ-002"])

    def test_no_pitfall_when_only_pass(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        self.sm.task_groups[0].validator_history = [{"round": 1, "verdict": "pass"}]
        _write_outbox(self.run_dir, "validator-g1-r1", "validation.md", _VALID_VALIDATION_PASS)
        result = ingest_lessons(self.sm)
        self.assertEqual(result["pitfalls"], [])

    # ---------- robustness ----------

    def test_missing_outbox_files_tolerated(self) -> None:
        # No agents written at all — should still write empty case shell, no crash.
        result = ingest_lessons(self.sm)
        self.assertIsNone(result["skipped"])
        self.assertEqual(len(result["cases"]), 1)

    def test_falls_back_to_workdir_when_project_root_unset(self) -> None:
        self.sm.project_root = None  # workdir still set
        result = ingest_lessons(self.sm)
        self.assertIsNone(result["skipped"])
        self.assertTrue(Path(result["cases"][0]).is_file())

    def test_spec_id_falls_back_to_run_id_when_missing(self) -> None:
        self.sm.spec_id = None
        result = ingest_lessons(self.sm)
        case = _read_yml(Path(result["cases"][0]))
        self.assertTrue(case["knowledge_id"].startswith("case-r1-"))

    # ---------- knowledge-base/ md twin ----------

    def test_case_md_twin_written_alongside_yml(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        _write_outbox(self.run_dir, "reviewer-g1-r1", "review.md", _VALID_REVIEW)
        result = ingest_lessons(self.sm)
        yml_path = Path(result["cases"][0])
        md_path = self.project / "knowledge-base" / "cases" / f"{yml_path.stem}.md"
        self.assertTrue(md_path.is_file(), f"missing twin md at {md_path}")
        body = md_path.read_text(encoding="utf-8")
        # frontmatter present
        self.assertTrue(body.startswith("---\n"))
        # title carries spec + group name
        self.assertIn("checkout pricing pipeline", body)
        # changed files surfaced
        self.assertIn("src/pricing.py", body)
        # implementation_summary surfaced
        self.assertIn("null-guard", body)

    def test_pit_md_twin_written_for_validator_fail(self) -> None:
        _write_outbox(self.run_dir, "coder-g1-s1-r1", "result.md", _CODER_RESULT)
        self.sm.task_groups[0].validator_history = [{"round": 1, "verdict": "fail"}]
        _write_outbox(self.run_dir, "validator-g1-r1", "validation.md", _VALID_VALIDATION_FAIL)
        result = ingest_lessons(self.sm)
        yml_path = Path(result["pitfalls"][0])
        md_path = self.project / "knowledge-base" / "pitfalls" / f"{yml_path.stem}.md"
        self.assertTrue(md_path.is_file(), f"missing twin md at {md_path}")
        body = md_path.read_text(encoding="utf-8")
        self.assertIn("BigDecimal.add NPE", body)
        self.assertIn("Optional.ofNullable", body)
        # affects section lists the file
        self.assertIn("src/pricing.py", body)
        # history line for first_seen_in
        self.assertIn("REQ-001", body)

    def test_knowledge_base_dirs_created_even_without_signal(self) -> None:
        result = ingest_lessons(self.sm)
        self.assertIsNone(result["skipped"])
        self.assertTrue((self.project / "knowledge-base" / "cases").is_dir())
        self.assertTrue((self.project / "knowledge-base" / "pitfalls").is_dir())


if __name__ == "__main__":
    unittest.main()
