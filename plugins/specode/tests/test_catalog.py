"""Tests for spec_session.py `on-user-prompt-catalog` hook (B2 description-as-trigger).

Catalog hook scans user prompt for keywords in CATALOG dict and emits a
"consider reading references/<X>.md" injection. Active-only — silent for
idle / ended / readonly to avoid noise in non-spec turns.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
REFS_DIR = REPO_ROOT / "plugins" / "specode" / "skills" / "specode" / "references"
CATALOG_PY = REPO_ROOT / "plugins" / "specode" / "scripts" / "spec_session" / "_catalog.py"


def _parse_hook(stdout: str) -> Optional[dict]:
    s = stdout.strip()
    if not s:
        return None
    return json.loads(s)


def _ctx(payload: Optional[dict]) -> str:
    if payload is None:
        return ""
    return payload.get("hookSpecificOutput", {}).get("additionalContext", "")


def _write_session(fake_home: Path, sid: str, **overrides) -> Path:
    sess_dir = fake_home / ".specode" / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "session_id": sid,
        "started_at": "2026-01-01T00:00:00Z",
        "last_activity_at": "2026-01-01T00:00:00Z",
        "ended_at": None,
        "mode": "idle",
        "active_spec_slug": None,
        "active_spec_dir": None,
        "spec_id": None,
        "phase": None,
        "lock_state": "released",
        "task_swarm_run_id": None,
        "pending_selector": None,
    }
    base.update(overrides)
    p = sess_dir / f"{sid}.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def _load_catalog_keys() -> set[str]:
    """Parse spec_session/_catalog.py CATALOG dict keys without importing the module."""
    src = CATALOG_PY.read_text(encoding="utf-8")
    m = re.search(
        r"CATALOG:\s*dict\[str,\s*list\[str\]\]\s*=\s*\{(.*?)\n\}\s*$",
        src,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "CATALOG dict not found in spec_session/_catalog.py"
    return set(re.findall(r'^\s*"([a-z][a-z0-9-]+)":', m.group(1), re.MULTILINE))


# --------------------------------------------------------------------------
# drift guards: CATALOG keys ↔ references/*.md ↔ frontmatter description
# --------------------------------------------------------------------------

def test_catalog_keys_have_matching_reference_files():
    """Every CATALOG key must point at a real references/<key>.md file."""
    keys = _load_catalog_keys()
    missing = sorted(k for k in keys if not (REFS_DIR / f"{k}.md").exists())
    assert not missing, f"CATALOG keys with no matching reference file: {missing}"


def test_every_catalog_referenced_file_has_description_frontmatter():
    """Each reference targeted by CATALOG must carry a non-empty `description:` field."""
    keys = _load_catalog_keys()
    bad: list[str] = []
    for k in sorted(keys):
        text = (REFS_DIR / f"{k}.md").read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            bad.append(f"{k}: no frontmatter")
            continue
        end = text.find("\n---\n", 4)
        if end < 0:
            bad.append(f"{k}: frontmatter not closed")
            continue
        fm = text[4:end]
        desc = None
        for line in fm.split("\n"):
            if line.startswith("description:"):
                desc = line[len("description:"):].strip()
                break
        if not desc:
            bad.append(f"{k}: empty or missing description")
    assert not bad, "frontmatter issues:\n  " + "\n  ".join(bad)


# --------------------------------------------------------------------------
# activation gate: only mode=active triggers
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["idle", "ended", "readonly"])
def test_catalog_silent_when_not_active(run_script, fake_home, make_session_id, mode):
    sid = make_session_id()
    _write_session(fake_home, sid, mode=mode)
    cp = run_script(
        "spec_session.py", "on-user-prompt-catalog",
        stdin=json.dumps({"session_id": sid, "prompt": "请讲一下 lock takeover heartbeat 流程"}),
    )
    assert cp.returncode == 0
    assert _parse_hook(cp.stdout) is None, f"mode={mode} should not emit"


def test_catalog_silent_when_session_missing(run_script, fake_home, make_session_id):
    sid = make_session_id()
    # no session file written
    cp = run_script(
        "spec_session.py", "on-user-prompt-catalog",
        stdin=json.dumps({"session_id": sid, "prompt": "task-swarm reviewer"}),
    )
    assert cp.returncode == 0
    assert _parse_hook(cp.stdout) is None


def test_catalog_silent_when_no_keyword_matches(run_script, fake_home, make_session_id):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="active")
    cp = run_script(
        "spec_session.py", "on-user-prompt-catalog",
        stdin=json.dumps({"session_id": sid, "prompt": "今天天气真好，散个步吧"}),
    )
    assert cp.returncode == 0
    assert _parse_hook(cp.stdout) is None


# --------------------------------------------------------------------------
# keyword matching: spot-check several CATALOG keys
# --------------------------------------------------------------------------

@pytest.mark.parametrize("prompt,expected_ref", [
    ("我需要 takeover 这个 spec", "lock-protocol"),
    ("锁主是谁？heartbeat 多久一次？", "lock-protocol"),
    ("vault 路径不对，要 --set-vault", "obsidian"),
    ("specs 目录在哪", "obsidian"),
    ("我想跑 task-swarm，让 reviewer 评审", "task-swarm"),
    ("调一下 AskUserQuestion 工具的 selector", "selectors"),
    ("EARS SHALL 怎么写", "templates"),
    ("迭代一下需求", "iteration"),
    ("workflow-choice 选哪一个", "workflow"),
])
def test_catalog_active_hits_expected_reference(
    run_script, fake_home, make_session_id, prompt, expected_ref,
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="active")
    cp = run_script(
        "spec_session.py", "on-user-prompt-catalog",
        stdin=json.dumps({"session_id": sid, "prompt": prompt}),
    )
    assert cp.returncode == 0
    ctx = _ctx(_parse_hook(cp.stdout))
    assert f"references/{expected_ref}.md" in ctx, (
        f"prompt {prompt!r} should hit {expected_ref}; got ctx:\n{ctx}"
    )
    # The injection must also carry the reference's description (frontmatter)
    assert "Use when" in ctx


def test_catalog_multi_hit_lists_all_and_deduplicates(
    run_script, fake_home, make_session_id,
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="active")
    prompt = (
        "我想 takeover 这个 spec，然后跑 task-swarm，让 reviewer 评审 — "
        "vault 在哪也告诉我下 obsidian"
    )
    cp = run_script(
        "spec_session.py", "on-user-prompt-catalog",
        stdin=json.dumps({"session_id": sid, "prompt": prompt}),
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    for expected in ("lock-protocol", "task-swarm", "obsidian"):
        # each ref appears exactly once (dedup)
        assert ctx.count(f"references/{expected}.md") == 1


def test_catalog_guard_off_emits_nothing(
    run_script, fake_home, make_session_id,
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="active")
    cp = run_script(
        "spec_session.py", "on-user-prompt-catalog",
        stdin=json.dumps({"session_id": sid, "prompt": "task-swarm reviewer"}),
        extra_env={"SPECODE_GUARD": "off"},
    )
    assert cp.returncode == 0
    assert _parse_hook(cp.stdout) is None
