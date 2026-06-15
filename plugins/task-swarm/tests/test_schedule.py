"""tests for _schedule.compute_schedule (pure topology + writes-conflict scheduler)."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from task_swarm._schedule import compute_schedule  # noqa: E402


def _g(gid, needs, writes, status):
    return {"id": gid, "needs": needs, "writes": writes, "status": status}


def test_all_pending_no_deps_no_conflict_all_runnable():
    groups = [_g("g1", [], ["a.py"], "pending"), _g("g2", [], ["b.py"], "pending")]
    s = compute_schedule(groups)
    assert set(s["runnable"]) == {"g1", "g2"}
    assert s["running"] == [] and s["done"] == [] and s["blocked"] == []


def test_needs_not_met_blocked():
    groups = [_g("g1", [], ["a.py"], "pending"), _g("g2", ["g1"], ["b.py"], "pending")]
    s = compute_schedule(groups)
    assert s["runnable"] == ["g1"]
    assert any(b["id"] == "g2" for b in s["blocked"])


def test_needs_met_unlocks():
    groups = [_g("g1", [], ["a.py"], "done"), _g("g2", ["g1"], ["b.py"], "pending")]
    s = compute_schedule(groups)
    assert s["runnable"] == ["g2"] and s["done"] == ["g1"]


def test_writes_conflict_with_running_serializes():
    groups = [_g("g1", [], ["a.py"], "running"), _g("g2", [], ["a.py"], "pending")]
    s = compute_schedule(groups)
    assert s["running"] == ["g1"]
    assert s["runnable"] == []
    assert any(b["id"] == "g2" and "conflict" in b["reason"] for b in s["blocked"])


def test_writes_disjoint_with_running_is_runnable():
    groups = [_g("g1", [], ["a.py"], "running"), _g("g2", [], ["b.py"], "pending")]
    s = compute_schedule(groups)
    assert s["runnable"] == ["g2"]


def test_upstream_failed_blocks_downstream():
    groups = [_g("g1", [], ["a.py"], "failed"), _g("g2", ["g1"], ["b.py"], "pending")]
    s = compute_schedule(groups)
    assert s["runnable"] == []
    assert any(b["id"] == "g2" and "failed" in b["reason"] for b in s["blocked"])


def test_running_and_done_classified():
    groups = [_g("g1", [], ["a.py"], "done"), _g("g2", [], ["b.py"], "running"),
              _g("g3", [], ["c.py"], "failed-deadloop")]
    s = compute_schedule(groups)
    assert s["done"] == ["g1"] and s["running"] == ["g2"]
    assert s["failed"] == ["g3"]
    assert "g3" not in s["runnable"] and "g3" not in s["running"]
