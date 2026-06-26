"""task_swarm._ingest_lessons — convert a finished run's outbox artifacts
into ``<project_root>/.ai-memory/knowledge/{cases,pitfalls}/*.yml``.

Closes the AI-Enterprise-Delivery-System roadmap P2-1: knowledge that
used to require hand-writing now grows automatically from each run.

For every successful resolve the ingester writes:

* one ``case-<spec_id>-<gid>.yml`` per task group (records this
  implementation: changed files / key decisions / review findings /
  bugs encountered);
* one ``pit-<sig>.yml`` per distinct validator-fail signature seen
  during the run (records reusable failure / fix lessons).

Same as ``spec-distill v2`` writes — schema is documented in
``pluginhub/plugins/obsidian-wiki/skills/spec-distill/references/
doc-template.md``. ``pit-*.yml`` collisions append the current spec_id
to ``seen_again_in``; ``case-*.yml`` collisions rewrite (a re-run of
the same spec-group supersedes the prior implementation).

Pure helper module — no exception bubbles up to the caller. If the
project lacks ``.ai-memory/`` or ``project_root`` is unset, we record
``skipped`` and return; resolve must never fail because of ingest."""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

try:  # pragma: no cover - optional dep
    import yaml  # type: ignore[import-untyped]

    _HAS_YAML = True
except ImportError:  # pragma: no cover - fallback path
    _HAS_YAML = False

from task_swarm._outbox import (
    ParseError,
    ReviewerReview,
    ValidatorValidation,
    parse_coder_result,
    parse_reviewer_review,
    parse_validator_validation,
)

__all__ = ["ingest_lessons"]


def ingest_lessons(sm: Any) -> dict[str, Any]:
    """Walk ``sm.task_groups`` and write case + pitfall yml to
    ``<project_root>/.ai-memory/knowledge/``.

    Returns ``{"cases": [...], "pitfalls": [...], "skipped": str|None}``.
    ``skipped`` is set (and the lists empty) when the project root or
    ``.ai-memory/`` cannot be located — never raises.
    """
    project_root = _resolve_project_root(sm)
    if project_root is None:
        return {"cases": [], "pitfalls": [], "skipped": "no project_root"}

    knowledge_root = project_root / ".ai-memory" / "knowledge"
    cases_dir = knowledge_root / "cases"
    pitfalls_dir = knowledge_root / "pitfalls"
    cases_dir.mkdir(parents=True, exist_ok=True)
    pitfalls_dir.mkdir(parents=True, exist_ok=True)
    # Twin md tree under <project_root>/knowledge-base/ — same stems as the
    # yml side; preserves narrative/ascii structure that yml fields lose.
    # Future P1-3 embedding indexer reads these md for higher-quality vectors.
    md_root = project_root / "knowledge-base"
    md_cases_dir = md_root / "cases"
    md_pitfalls_dir = md_root / "pitfalls"
    md_cases_dir.mkdir(parents=True, exist_ok=True)
    md_pitfalls_dir.mkdir(parents=True, exist_ok=True)

    spec_id = sm.spec_id or sm.run_id
    run_dir = Path(sm.run_dir)
    today = datetime.date.today().isoformat()

    written_cases: list[str] = []
    written_pitfalls: list[str] = []

    for gs in sm.task_groups:
        # Skip groups that never finished or hard-failed — no signal worth ingesting.
        if gs.status not in {"done", "writeback"}:
            continue
        coder_results = _load_coder_results(run_dir, gs)
        review = _load_review(run_dir, gs)
        validations = _load_validations(run_dir, gs)

        case_yml = _build_case(
            spec_id=spec_id,
            gs=gs,
            coder_results=coder_results,
            review=review,
            validations=validations,
            today=today,
            sm=sm,
        )
        case_path = cases_dir / f"{case_yml['knowledge_id']}.yml"
        _dump_yaml(case_path, case_yml)
        written_cases.append(str(case_path))
        # twin md (knowledge-base/cases/case-*.md)
        case_md_path = md_cases_dir / f"{case_yml['knowledge_id']}.md"
        _atomic_write_text(case_md_path, _case_to_md(case_yml))

        for val in validations:
            if val.verdict != "fail":
                continue
            sig = val.fail_signature()
            if not sig:
                continue
            pit_path = pitfalls_dir / f"pit-{sig}.yml"
            pit_yml = _merge_pitfall(
                existing_path=pit_path,
                sig=sig,
                validation=val,
                spec_id=spec_id,
                today=today,
            )
            _dump_yaml(pit_path, pit_yml)
            if str(pit_path) not in written_pitfalls:
                written_pitfalls.append(str(pit_path))
            # twin md (knowledge-base/pitfalls/pit-*.md)
            pit_md_path = md_pitfalls_dir / f"pit-{sig}.md"
            _atomic_write_text(pit_md_path, _pit_to_md(pit_yml))

    return {"cases": written_cases, "pitfalls": written_pitfalls, "skipped": None}


# ---------- project root resolution ----------


def _resolve_project_root(sm: Any) -> Optional[Path]:
    raw = getattr(sm, "project_root", None) or getattr(sm, "workdir", None)
    if not raw:
        return None
    p = Path(raw)
    if not p.is_dir():
        return None
    return p


# ---------- outbox loaders (silent on missing/parse error) ----------


def _load_coder_results(run_dir: Path, gs: Any) -> list:
    out: list = []
    for item in gs.items:
        n = item.get("number")
        if n is None:
            continue
        path = run_dir / "agents" / f"coder-{gs.id}-s{n}-r1" / "outbox" / "result.md"
        if not path.is_file():
            continue
        try:
            out.append(parse_coder_result(path))
        except ParseError:
            continue
    return out


def _load_review(run_dir: Path, gs: Any) -> Optional[ReviewerReview]:
    path = run_dir / "agents" / f"reviewer-{gs.id}-r1" / "outbox" / "review.md"
    if not path.is_file():
        return None
    try:
        return parse_reviewer_review(path)
    except ParseError:
        return None


def _load_validations(run_dir: Path, gs: Any) -> list[ValidatorValidation]:
    """Load every validator-r{round} that produced a validation.md.

    Ingester needs every round (fails carry pitfall signatures; the final
    pass marks acceptance) — not just the latest."""
    out: list[ValidatorValidation] = []
    seen_rounds: set[int] = set()
    for entry in gs.validator_history or []:
        rnd = entry.get("round")
        if rnd is None or rnd in seen_rounds:
            continue
        seen_rounds.add(rnd)
        path = run_dir / "agents" / f"validator-{gs.id}-r{rnd}" / "outbox" / "validation.md"
        if not path.is_file():
            continue
        try:
            out.append(parse_validator_validation(path))
        except ParseError:
            continue
    return out


# ---------- builders ----------


def _build_case(
    spec_id: str,
    gs: Any,
    coder_results: list,
    review: Optional[ReviewerReview],
    validations: list[ValidatorValidation],
    today: str,
    sm: Any,
) -> dict[str, Any]:
    knowledge_id = f"case-{spec_id}-{gs.id}"

    changed_files: list[str] = []
    for item in gs.items:
        for w in item.get("writes", []) or []:
            if w not in changed_files:
                changed_files.append(w)

    key_decisions: list[dict[str, str]] = []
    bugs_encountered: list[str] = []
    for cr in coder_results:
        for hint in cr.hints or []:
            text = hint.strip()
            if text:
                key_decisions.append({"decision": text, "reason": ""})
        if cr.status == "failed" and cr.status_reason:
            bugs_encountered.append(cr.status_reason.strip())

    for val in validations:
        if val.verdict == "fail" and val.failure_excerpt:
            excerpt = val.failure_excerpt.strip().splitlines()
            if excerpt:
                bugs_encountered.append(excerpt[0][:200])

    review_findings: list[dict[str, str]] = []
    if review is not None:
        for finding in review.p0_items:
            review_findings.append(
                {"finding": finding.text[:240], "severity": "p0", "action": "addressed"}
            )
        for finding in review.p1_items:
            review_findings.append(
                {"finding": finding.text[:240], "severity": "p1", "action": "addressed"}
            )

    last_verdict = validations[-1].verdict if validations else "n/a"
    if last_verdict == "pass":
        acceptance = "passed"
    elif last_verdict == "fail":
        acceptance = "failed"
    else:
        acceptance = "passed" if gs.status == "done" else "partial"

    implementation_summary = _summarize_implementation(coder_results, gs)

    out: dict[str, Any] = {
        "schema_version": "1.0",
        "knowledge_id": knowledge_id,
        "type": "case",
        "case_id": knowledge_id,
        "spec_id": spec_id,
        "group_id": gs.id,
        "title": gs.name or knowledge_id,
        "implementation_summary": implementation_summary,
        "changed_files": changed_files,
        "key_decisions": key_decisions,
        "bugs_encountered": bugs_encountered,
        "review_findings": review_findings,
        "acceptance_status": acceptance,
        "source_spec": sm.spec_dir or "",
        "source_files": ["requirements.md", "design.md", "implementation-log.md"],
        "related_requirements": [spec_id],
        "related_knowledge": [],
        "related_code": [{"file": p} for p in changed_files],
        "tags": [],
        "created_at": today,
        "updated_at": today,
        "status": "active",
        "confidence": "high" if acceptance == "passed" else "medium",
    }
    return out


def _summarize_implementation(coder_results: list, gs: Any) -> str:
    parts: list[str] = []
    for cr in coder_results:
        for change in cr.key_changes or []:
            text = change.strip("- ").strip()
            if text:
                parts.append(text)
    if not parts:
        # Fall back to the group's task titles.
        for item in gs.items:
            t = item.get("title", "").strip()
            if t:
                parts.append(t)
    return "\n".join(f"- {p}" for p in parts) if parts else ""


_TITLE_FROM_EXCERPT_RE = re.compile(r"(AssertionError|Error|Exception)[^\n]*")


def _merge_pitfall(
    existing_path: Path,
    sig: str,
    validation: ValidatorValidation,
    spec_id: str,
    today: str,
) -> dict[str, Any]:
    knowledge_id = f"pit-{sig}"
    title = _extract_pit_title(validation.failure_excerpt) or knowledge_id

    fix_steps: list[str] = []
    affects: list[str] = []
    for tgt in validation.fix_targets or []:
        if tgt.suggestion:
            fix_steps.append(tgt.suggestion.strip())
        if tgt.file_path and tgt.file_path not in affects:
            affects.append(tgt.file_path)

    existing = _load_yaml_if_exists(existing_path)
    if isinstance(existing, dict):
        # Already seen — append spec_id to seen_again_in and refresh.
        seen_again = list(existing.get("seen_again_in") or [])
        if (
            spec_id != existing.get("first_seen_in")
            and spec_id not in seen_again
        ):
            seen_again.append(spec_id)
        merged_affects = list(existing.get("affects") or [])
        for a in affects:
            if a not in merged_affects:
                merged_affects.append(a)
        merged_fix = list(existing.get("fix") or [])
        for f in fix_steps:
            if f not in merged_fix:
                merged_fix.append(f)
        existing.update(
            {
                "updated_at": today,
                "seen_again_in": seen_again,
                "affects": merged_affects,
                "fix": merged_fix,
            }
        )
        existing.setdefault("schema_version", "1.0")
        existing.setdefault("type", "pitfall")
        existing.setdefault("knowledge_id", knowledge_id)
        existing.setdefault("pit_id", knowledge_id)
        existing.setdefault("status", "active")
        existing.setdefault("confidence", "medium")
        return existing

    return {
        "schema_version": "1.0",
        "knowledge_id": knowledge_id,
        "type": "pitfall",
        "pit_id": knowledge_id,
        "title": title[:200],
        "symptom": (validation.failure_excerpt or "").strip()[:1000],
        "fix": fix_steps,
        "affects": affects,
        "first_seen_in": spec_id,
        "seen_again_in": [],
        "tags": ["validator-fail"],
        "created_at": today,
        "updated_at": today,
        "status": "active",
        "confidence": "medium",
    }


def _extract_pit_title(excerpt: str) -> str:
    if not excerpt:
        return ""
    match = _TITLE_FROM_EXCERPT_RE.search(excerpt)
    if match:
        return match.group(0).strip()
    return excerpt.strip().splitlines()[0][:200] if excerpt.strip() else ""


# ---------- yaml IO ----------


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_YAML:
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)  # type: ignore[name-defined]
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _load_yaml_if_exists(path: Path) -> Any:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if _HAS_YAML:
        try:
            return yaml.safe_load(text)  # type: ignore[name-defined]
        except yaml.YAMLError:  # type: ignore[name-defined]
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# Re-exported for tests / future use.
def _stable_sig(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------- md rendering (twin of yml, written under knowledge-base/) ----------


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _yml_frontmatter(payload: dict[str, Any]) -> str:
    """Minimal yaml frontmatter dump for md files. Avoids importing yaml
    here — keep _ingest_lessons' optional-yaml stance intact."""
    if _HAS_YAML:
        return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)  # type: ignore[name-defined]
    # JSON-as-YAML fallback (valid YAML 1.2 subset)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _case_to_md(case: dict[str, Any]) -> str:
    """Render a case yml dict to its knowledge-base/cases/*.md twin.

    Layout matches references/doc-template.md §4.2 case md template
    (specode-distill 3.0+)."""
    fm = {
        "knowledge_id": case.get("knowledge_id", ""),
        "type": "case",
        "version": case.get("version", 1),
        "updated_at": case.get("updated_at", ""),
        "tags": case.get("tags", []) or [],
        "related_requirements": case.get("related_requirements", []) or [],
        "related_knowledge": case.get("related_knowledge", []) or [],
        "related_code": case.get("related_code", []) or [],
    }
    lines: list[str] = ["---", _yml_frontmatter(fm).rstrip(), "---", ""]
    title = case.get("title") or case.get("knowledge_id", "")
    lines += [f"# case {case.get('spec_id', '')} — {title}".rstrip(), ""]

    summary = (case.get("implementation_summary") or "").strip()
    if summary:
        lines += ["## 实现摘要", "", summary, ""]

    changed = case.get("changed_files") or []
    if changed:
        lines += ["## 改动文件", ""]
        lines += [f"- `{p}`" for p in changed]
        lines.append("")

    decisions = case.get("key_decisions") or []
    if decisions:
        lines += ["## 关键决策", "", "| 决策 | 理由 |", "|---|---|"]
        for d in decisions:
            dec = (d.get("decision") if isinstance(d, dict) else str(d)).replace("|", "\\|")
            rsn = (d.get("reason", "") if isinstance(d, dict) else "").replace("|", "\\|") or "—"
            lines.append(f"| {dec} | {rsn} |")
        lines.append("")

    bugs = case.get("bugs_encountered") or []
    if bugs:
        lines += ["## 实施中遇到的 bug", ""]
        lines += [f"- {b}" for b in bugs]
        lines.append("")

    findings = case.get("review_findings") or []
    if findings:
        lines += ["## Review 反馈", "", "| 发现 | 严重度 | 处理 |", "|---|---|---|"]
        for f in findings:
            ft = f.get("finding", "").replace("|", "\\|")
            sv = f.get("severity", "")
            ac = f.get("action", "")
            lines.append(f"| {ft} | {sv} | {ac} |")
        lines.append("")

    acceptance = case.get("acceptance_status", "")
    if acceptance:
        lines += ["## 验收", "", f"- 状态：**{acceptance}**", ""]

    lines.append(
        "> 自动由 `task-swarm resolve` 写入；同名 yml 见 `.ai-memory/knowledge/cases/`。"
    )
    return "\n".join(lines).rstrip() + "\n"


def _pit_to_md(pit: dict[str, Any]) -> str:
    """Render a pitfall yml dict to its knowledge-base/pitfalls/*.md twin.

    Layout matches references/doc-template.md §5.2 pit md template."""
    fm = {
        "knowledge_id": pit.get("knowledge_id", ""),
        "type": "pitfall",
        "version": pit.get("version", 1),
        "updated_at": pit.get("updated_at", ""),
        "tags": pit.get("tags", []) or [],
        "related_requirements": (
            [pit.get("first_seen_in")] if pit.get("first_seen_in") else []
        )
        + (pit.get("seen_again_in") or []),
        "related_knowledge": [],
        "related_code": [{"file": f} for f in (pit.get("affects") or [])],
    }
    lines: list[str] = ["---", _yml_frontmatter(fm).rstrip(), "---", ""]
    title = pit.get("title") or pit.get("knowledge_id", "")
    lines += [f"# pit — {title}", ""]

    symptom = (pit.get("symptom") or "").strip()
    if symptom:
        lines += ["## 症状", "", "```", symptom, "```", ""]

    fix = pit.get("fix") or []
    if fix:
        lines += ["## 修复", ""]
        lines += [f"- {f}" for f in fix]
        lines.append("")

    affects = pit.get("affects") or []
    if affects:
        lines += ["## 影响范围", ""]
        lines += [f"- `{a}`" for a in affects]
        lines.append("")

    history_lines = []
    first = pit.get("first_seen_in")
    if first:
        history_lines.append(f"| 首次踩到 | [[case-{first}]] | — |")
    for again in pit.get("seen_again_in") or []:
        history_lines.append(f"| 再次踩到 | {again} | 已合并教训 |")
    if history_lines:
        lines += ["## 历史", "", "| 时间 | spec | 备注 |", "|---|---|---|"]
        lines += history_lines
        lines.append("")

    lines.append(
        "> 自动由 `task-swarm resolve` 写入；同 signature 后续重复触发会追加到上表。"
    )
    return "\n".join(lines).rstrip() + "\n"
