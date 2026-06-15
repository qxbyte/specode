"""tests for task_swarm._state — GroupState per-group 子状态机 + 死循环检测 + run 级 IO。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._state import (  # noqa: E402
    StateMachine, GroupState, DEADLOOP_THRESHOLD,
)


def _gs(gid: str = "g1", items=None) -> GroupState:
    return GroupState(id=gid, name=f"组{gid}", writes=["f1.py"],
                      items=items or [{"number": "1.1", "title": "t", "writes": ["f1.py"],
                                       "reads": [], "requirements": ["1.1"]}])


def _make_sm(tmp_path: Path, num_groups: int = 2) -> StateMachine:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    task_groups = [_gs(f"g{i}") for i in range(1, num_groups + 1)]
    sm = StateMachine(run_id="rid-1", tasks_md="", run_dir=str(run_dir),
                      task_groups=task_groups)
    sm.save()
    return sm


# ---- run 级 IO / 迁移 ----

def test_save_and_load_roundtrip(tmp_path):
    sm = _make_sm(tmp_path)
    sm2 = StateMachine.load(Path(sm.run_dir))
    assert sm2.run_id == sm.run_id
    assert len(sm2.task_groups) == len(sm.task_groups)
    assert sm2.task_groups[0].id == "g1"


def test_load_migrates_legacy_claude_session_id(tmp_path):
    sm = _make_sm(tmp_path)
    state_path = StateMachine.state_path(Path(sm.run_dir))
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data.pop("session_id", None)
    data["claude_session_id"] = "legacy-sess-xyz"
    state_path.write_text(json.dumps(data), encoding="utf-8")
    sm2 = StateMachine.load(Path(sm.run_dir))
    assert sm2.session_id == "legacy-sess-xyz"


def test_events_append_timestamps(tmp_path):
    sm = _make_sm(tmp_path)
    sm.events_append({"type": "test"})
    assert len(sm.events) == 1
    assert "at" in sm.events[0]


def test_state_save_atomic_then_load(tmp_path):
    sm = _make_sm(tmp_path)
    sm.task_groups[0].round = 7
    sm.save()
    sm2 = StateMachine.load(Path(sm.run_dir))
    assert sm2.task_groups[0].round == 7


# ---- GroupState per-group 子状态机 ----

def test_begin_coding_sets_in_flight():
    gs = _gs("g1")
    gs.begin_coding()
    assert gs.phase == "coding"
    assert gs.round == 1
    assert gs.status == "coding"
    assert gs.coder_in_flight == ["coder-g1-s1.1-r1"]


def test_mark_coder_done():
    gs = _gs("g1")
    gs.begin_coding()
    gs.mark_coder_done("coder-g1-s1.1-r1")
    assert gs.coder_in_flight == []
    assert gs.coder_done == ["coder-g1-s1.1-r1"]
    assert gs.all_coders_returned()


def test_begin_review_then_validation():
    gs = _gs("g1")
    gs.begin_coding()
    gs.mark_coder_done("coder-g1-s1.1-r1")
    gs.begin_review()
    assert gs.phase == "review"
    gs.mark_reviewer_done()
    gs.begin_validation()
    assert gs.phase == "validation"


def test_p0_fix_phase():
    gs = _gs("g1")
    gs.begin_coding()
    gs.begin_review()
    gs.mark_reviewer_done()
    pending = [{"text": "x", "evidence_tags": ["req:1.1"], "file_hint": "f1.py"},
               {"text": "y", "evidence_tags": ["security"], "file_hint": "f2.py"}]
    gs.begin_p0_fix(pending)
    assert gs.phase == "p0-fix"
    assert len(gs.p0_in_flight) == 2  # 2 unique files
    assert gs.p0_in_flight[0] == "coder-p0fix-g1-r1-f0"


def test_v_fix_phase_round_increment():
    gs = _gs("g1")
    gs.begin_coding()
    gs.begin_review()
    gs.mark_reviewer_done()
    gs.begin_validation()
    gs.mark_validator_done()
    gs.record_round_signature("fail_sig_1")
    initial_round = gs.round
    gs.begin_v_fix([{"file_path": "f1.py"}])
    assert gs.phase == "v-fix"
    assert gs.round == initial_round + 1
    assert gs.vfix_in_flight == [f"coder-vfix-g1-r{gs.round}-f0"]


def test_deadloop_threshold():
    gs = _gs("g1")
    for i in range(DEADLOOP_THRESHOLD):
        gs.round = i + 1
        gs.record_round_signature("samesig")
    assert gs.detect_deadloop()


def test_deadloop_not_triggered_with_different_sigs():
    gs = _gs("g1")
    for i, sig in enumerate(["a", "b", "c"]):
        gs.round = i + 1
        gs.record_round_signature(sig)
    assert not gs.detect_deadloop()


def test_deadloop_below_threshold():
    gs = _gs("g1")
    for i in range(DEADLOOP_THRESHOLD - 1):
        gs.round = i + 1
        gs.record_round_signature("samesig")
    assert not gs.detect_deadloop()


def test_finalize_sets_status():
    gs = _gs("g1")
    gs.begin_coding()
    gs.finalize("done")
    assert gs.status == "done"
    assert gs.phase == "done"


def test_fail_deadloop_sets_status():
    gs = _gs("g1")
    gs.begin_coding()
    gs.fail_deadloop()
    assert gs.status == "failed-deadloop"
    assert gs.phase == "error"


def test_groupstate_roundtrip():
    gs = GroupState(id="g1", name="A", needs=["g0"], writes=["a.py"],
                    items=[{"number": "1.1", "title": "t"}], status="coding")
    d = gs.to_dict()
    gs2 = GroupState.from_dict(d)
    assert gs2.id == "g1" and gs2.needs == ["g0"] and gs2.status == "coding"
    assert gs2.sched_view() == {"id": "g1", "needs": ["g0"], "writes": ["a.py"], "status": "coding"}


def test_load_migrates_legacy_linear_schema(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    legacy = {
        "run_id": "r1", "tasks_md": "", "run_dir": str(run_dir),
        "groups": [[{"number": "1.1", "title": "t", "writes": ["a.py"], "reads": [],
                     "depends_on": [], "requirements": [], "items": [],
                     "header_line_no": 0, "end_line_no": 0}]],
        "group_status": ["coding"], "current_group_index": 0,
        "phase": "coding", "round": 1, "coder_in_flight": ["coder-g1-s1.1-r1"],
    }
    (run_dir / "state.json").write_text(json.dumps(legacy), encoding="utf-8")
    sm = StateMachine.load(run_dir)
    assert len(sm.task_groups) == 1
    g = sm.task_groups[0]
    assert g.id == "g1" and g.status == "coding" and g.phase == "coding"
    assert g.coder_in_flight == ["coder-g1-s1.1-r1"]
