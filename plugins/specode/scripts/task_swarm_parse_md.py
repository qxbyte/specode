"""tasks.md parser for task-swarm.

Extracts the dispatch plan from a specode-style tasks.md:
  - top-level stages (`- [ ] N. 标题`)
  - leaf tasks (`  - [ ] N.M 标题`)
  - checkpoint stages (top-level + title contains "检查点")
  - leaf metadata: `文件:` / `验证:` / `_需求:x.y_`
  - `@swarm:full | coder-only | skip` tags + heuristic defaults

Outputs a structured plan: stage list, deps (sequential by default), parallel
groups (stages with disjoint file sets), warnings.

This module is pure-function: input is tasks.md text, output is dict (JSON-safe).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Iterable


# ---------- regex ----------

# Top-level stage: `- [ ] N. 标题` (allow [x] / [~] / [*] markers).
STAGE_RE = re.compile(r"^- \[([ x~*\-])\] (\d+)\. (.+?)\s*$")

# Leaf task: 2-space indent + `- [ ] N.M 标题`.
LEAF_RE = re.compile(r"^  - \[([ x~*\-])\] (\d+\.\d+) (.+?)\s*$")

# Metadata lines under a leaf (4-space indent).
FILE_RE = re.compile(r"^    - (?:文件|files?)[：:]\s*(.+?)\s*$", re.IGNORECASE)
VERIFY_RE = re.compile(r"^    - (?:验证|verify)[：:]\s*(.+?)\s*$", re.IGNORECASE)
REQ_RE = re.compile(r"^    - _(?:需求|requirements?)[：:]\s*(.+?)_\s*$", re.IGNORECASE)

# `@swarm:xxx` tags anywhere in a leaf title or metadata.
TAG_RE = re.compile(r"@swarm:(\w[\w-]*)")

VALID_TAGS = {"full", "coder-only", "skip"}

CHECKPOINT_KEYWORDS = ("检查点", "checkpoint")


# ---------- data classes ----------

@dataclass
class Leaf:
    num: str                       # "1.1"
    title: str
    files: list[str] = field(default_factory=list)
    verify: str = ""
    requirement: str = ""
    tags_raw: list[str] = field(default_factory=list)   # ["full", "coder-only", ...]
    policy: str = "default"        # final decision: full | coder-only | skip | default
    optional: bool = False         # came from `[*]` marker
    line: int = 0                  # original line number (1-based)


@dataclass
class Stage:
    num: int
    title: str
    kind: str                      # "stage" | "checkpoint"
    leaves: list[Leaf] = field(default_factory=list)
    deps: list[int] = field(default_factory=list)   # stage numbers
    files_union: list[str] = field(default_factory=list)
    optional: bool = False
    checkpoint_for: int | None = None
    line: int = 0


@dataclass
class Plan:
    stages: list[Stage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stages": [asdict(s) for s in self.stages],
            "warnings": list(self.warnings),
        }


# ---------- parsing ----------

def parse_tasks_md(text: str) -> Plan:
    """Parse tasks.md text → Plan.

    Lenient — unknown lines are ignored. Errors that affect dispatch (missing
    files for full-mode leaves, malformed numbers) are surfaced as warnings.
    """
    plan = Plan()
    current_stage: Stage | None = None
    current_leaf: Leaf | None = None

    lines = text.splitlines()
    for idx, raw in enumerate(lines, start=1):
        # Stage match must come first since leaves are also dashes.
        m_stage = STAGE_RE.match(raw)
        if m_stage:
            current_leaf = None
            marker, num_s, title = m_stage.group(1), m_stage.group(2), m_stage.group(3)
            num = int(num_s)
            kind = "checkpoint" if any(kw in title for kw in CHECKPOINT_KEYWORDS) else "stage"
            stage = Stage(
                num=num,
                title=title.strip(),
                kind=kind,
                optional=(marker == "*"),
                line=idx,
            )
            plan.stages.append(stage)
            current_stage = stage
            continue

        m_leaf = LEAF_RE.match(raw)
        if m_leaf and current_stage is not None:
            marker, leaf_num, title = m_leaf.group(1), m_leaf.group(2), m_leaf.group(3)
            tags = TAG_RE.findall(title)
            # Strip tag suffixes from the title for cleanliness.
            clean_title = TAG_RE.sub("", title).rstrip()
            leaf = Leaf(
                num=leaf_num,
                title=clean_title,
                tags_raw=list(tags),
                optional=(marker == "*"),
                line=idx,
            )
            current_stage.leaves.append(leaf)
            current_leaf = leaf
            continue

        if current_leaf is None:
            continue

        m_file = FILE_RE.match(raw)
        if m_file:
            for fp in _split_files(m_file.group(1)):
                current_leaf.files.append(fp)
            # Tags can also live on the file line.
            current_leaf.tags_raw.extend(TAG_RE.findall(raw))
            continue
        m_verify = VERIFY_RE.match(raw)
        if m_verify:
            current_leaf.verify = m_verify.group(1).strip()
            current_leaf.tags_raw.extend(TAG_RE.findall(raw))
            continue
        m_req = REQ_RE.match(raw)
        if m_req:
            current_leaf.requirement = m_req.group(1).strip()
            current_leaf.tags_raw.extend(TAG_RE.findall(raw))
            continue

        # Plain tag line under a leaf (e.g., "    - @swarm:full").
        tags_on_line = TAG_RE.findall(raw)
        if tags_on_line:
            current_leaf.tags_raw.extend(tags_on_line)

    # Post-process: tag arbitration, deps, file unions.
    _arbitrate_tags(plan)
    _link_checkpoints(plan)
    _compute_file_unions(plan)
    _compute_deps(plan)
    return plan


def _split_files(raw: str) -> list[str]:
    out: list[str] = []
    for piece in re.split(r"[,，]", raw):
        piece = piece.strip().strip("`").strip()
        if piece:
            out.append(piece)
    return out


# ---------- tag arbitration ----------

def _arbitrate_tags(plan: Plan) -> None:
    """Resolve `@swarm:*` tags + heuristic defaults per leaf.

    Priority (high → low):
      1. @swarm:skip wins unconditionally.
      2. Explicit @swarm:full > @swarm:coder-only.
      3. Explicit any-tag overrides heuristic.
      4. Heuristic: optional ([*]) OR no `_需求:_` → coder-only.
      5. Otherwise: default (stage-aggregated).

    Unknown tags → warning + ignored.
    """
    for stage in plan.stages:
        for leaf in stage.leaves:
            explicit: set[str] = set()
            for t in leaf.tags_raw:
                if t in VALID_TAGS:
                    explicit.add(t)
                else:
                    plan.warnings.append(
                        f"[WARN] T{leaf.num} 无效 @swarm: 标签 \"{t}\"，已忽略"
                    )
            # Dedup tags_raw to valid only (preserves what user wrote, normalized).
            leaf.tags_raw = sorted(explicit)

            if "skip" in explicit:
                if explicit - {"skip"}:
                    plan.warnings.append(
                        f"[INFO] T{leaf.num} 标签冲突 {sorted(explicit)} → 采用 skip"
                    )
                leaf.policy = "skip"
                continue
            if "full" in explicit and "coder-only" in explicit:
                plan.warnings.append(
                    f"[INFO] T{leaf.num} 标签冲突 @swarm:full + @swarm:coder-only → 采用 full"
                )
                leaf.policy = "full"
                continue
            if "full" in explicit:
                leaf.policy = "full"
                continue
            if "coder-only" in explicit:
                leaf.policy = "coder-only"
                continue
            # heuristic
            if leaf.optional or not leaf.requirement:
                leaf.policy = "coder-only"
            else:
                leaf.policy = "default"


# ---------- deps + parallelism ----------

def _link_checkpoints(plan: Plan) -> None:
    """Link each checkpoint stage to the previous non-checkpoint stage."""
    last_stage_num: int | None = None
    for stage in plan.stages:
        if stage.kind == "stage":
            last_stage_num = stage.num
        else:
            stage.checkpoint_for = last_stage_num


def _compute_file_unions(plan: Plan) -> None:
    for stage in plan.stages:
        seen: set[str] = set()
        union: list[str] = []
        for leaf in stage.leaves:
            if leaf.policy == "skip":
                continue
            for f in leaf.files:
                if f not in seen:
                    seen.add(f)
                    union.append(f)
        stage.files_union = union


def _compute_deps(plan: Plan) -> None:
    """Compute stage-level deps.

    Default rule:
      - A checkpoint stage depends on the stage it follows (checkpoint_for).
      - Otherwise, deps stay empty (potential parallelism is determined by
        file-union disjointness at dispatch time, not encoded here).

    Future versions may parse explicit `@depends-on:N` tags from stage titles.
    """
    for stage in plan.stages:
        if stage.kind == "checkpoint" and stage.checkpoint_for is not None:
            stage.deps = [stage.checkpoint_for]


# ---------- helpers used by orchestrator ----------

def parallelizable(a: Stage, b: Stage) -> bool:
    """Two stages may run in parallel if their file unions are disjoint and
    neither depends on the other.
    """
    if a.num in b.deps or b.num in a.deps:
        return False
    fa = set(a.files_union)
    fb = set(b.files_union)
    return not (fa & fb)


def stages_with_role(plan: Plan, role: str) -> Iterable[Stage]:
    """Yield stages that need the given role to be dispatched.

    - role='coder' or 'reviewer': stages with at least one non-skip leaf and
      at least one leaf with policy in {full, default, coder-only}.
      (coder-only leaves get coder but skip reviewer; the reviewer call still
      happens for the stage if ANY default/full leaf is present.)
    - role='validator': only stages of kind 'checkpoint'.
    """
    if role == "validator":
        for s in plan.stages:
            if s.kind == "checkpoint":
                yield s
        return
    for s in plan.stages:
        if s.kind != "stage":
            continue
        non_skip = [l for l in s.leaves if l.policy != "skip"]
        if not non_skip:
            continue
        if role == "coder":
            yield s
            continue
        if role == "reviewer":
            if any(l.policy in {"full", "default"} for l in s.leaves):
                yield s


def parse_file(path) -> Plan:
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8")
    return parse_tasks_md(text)
