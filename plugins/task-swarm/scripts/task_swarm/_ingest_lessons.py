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
import subprocess
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
    """Aggregate a finished run into one case-per-spec plus per-signature
    pitfalls, written through the single knowledge writer.

    FIX-2: payloads are routed to ``codemap knowledge write`` when the CLI is
    available (the one deterministic writer that owns id / schema / dates /
    merge); otherwise an inline fallback keeps task-swarm self-contained.

    Returns ``{"cases": [...], "pitfalls": [...], "skipped": str|None}``.
    Never raises — resolve must not fail because of ingest.
    """
    project_root = _resolve_project_root(sm)
    if project_root is None:
        return {"cases": [], "pitfalls": [], "skipped": "no project_root"}

    _ensure_dirs(project_root)

    spec_id = sm.spec_id or sm.run_id
    run_dir = Path(sm.run_dir)
    today = datetime.date.today().isoformat()

    done_groups = [gs for gs in sm.task_groups if gs.status in {"done", "writeback"}]

    written_cases: list[str] = []
    written_pitfalls: list[str] = []

    # One canonical case per spec (FIX-2 / ISSUE-2), aggregating all groups —
    # so its id (case-<spec_id>) matches the human specode-distill case and the
    # documented supersede actually fires.
    if done_groups:
        fields, md_body = _build_case_fields(spec_id, done_groups, run_dir, sm)
        payload = {"spec_id": spec_id, "fields": fields, "md_body": md_body}
        res = _write_payload(project_root, "cases", payload, today)
        if res and res.get("yml_path"):
            written_cases.append(res["yml_path"])

    # Pitfalls: one per distinct validator-fail signature (writer merges
    # repeats via seen_again_in).
    for gs in done_groups:
        for val in _load_validations(run_dir, gs):
            if val.verdict != "fail":
                continue
            sig = val.fail_signature()
            if not sig:
                continue
            fields = _build_pit_fields(val, spec_id)
            payload = {"signature": sig, "spec_id": spec_id, "fields": fields}
            res = _write_payload(project_root, "pitfalls", payload, today)
            if res and res.get("yml_path") and res["yml_path"] not in written_pitfalls:
                written_pitfalls.append(res["yml_path"])

    return {"cases": written_cases, "pitfalls": written_pitfalls, "skipped": None}


def _ensure_dirs(project_root: Path) -> None:
    for sub in ("cases", "pitfalls"):
        (project_root / ".ai-memory" / "knowledge" / sub).mkdir(parents=True, exist_ok=True)
        (project_root / "knowledge-base" / sub).mkdir(parents=True, exist_ok=True)


# ---------- write dispatch: codemap CLI (single writer) → inline fallback ----------


def _write_payload(
    project_root: Path, category: str, payload: dict[str, Any], today: str
) -> Optional[dict[str, Any]]:
    res = _codemap_write(project_root, category, payload)
    if res is not None:
        return res
    return _inline_write(project_root, category, payload, today)


def _codemap_write(
    project_root: Path, category: str, payload: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Route a payload to ``codemap knowledge write``. Returns the parsed
    result dict when codemap ran, or ``None`` when the CLI is absent / crashed
    (caller then falls back to the inline writer). Never raises."""
    argv = [
        "codemap", "knowledge", "write",
        "--project", str(project_root),
        "--category", category,
        "--payload", "-",
        "-o", "json",
    ]
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    try:
        result = json.loads(proc.stdout)
    except (ValueError, json.JSONDecodeError):
        return None
    return result if isinstance(result, dict) else None


def _inline_write(
    project_root: Path, category: str, payload: dict[str, Any], today: str
) -> dict[str, Any]:
    if category == "cases":
        return _inline_write_case(project_root, payload, today)
    return _inline_write_pitfall(project_root, payload, today)


# ---------- project root resolution ----------


def _read_frontmatter_project_root(sm: Any) -> Optional[Path]:
    """Read project_root from the spec's requirements.md YAML frontmatter.

    This is the single source of truth (FIX-1): the same byte distill reads.
    Returns the path only when present AND an existing directory, so a stale
    or malformed frontmatter cleanly falls through to the legacy fallback.
    stdlib-only line parsing (yaml is optional in this plugin)."""
    spec_dir = getattr(sm, "spec_dir", None)
    if not spec_dir:
        return None
    p = Path(spec_dir)
    if not p.is_absolute():
        workdir = getattr(sm, "workdir", None)
        if workdir:
            p = Path(workdir) / p
    req = p / "requirements.md"
    if not req.is_file():
        return None
    try:
        text = req.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        line = lines[i]
        if line.startswith("project_root:"):
            val = line[len("project_root:") :].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            if not val:
                return None
            candidate = Path(val)
            return candidate if candidate.is_dir() else None
    return None


def _resolve_project_root(sm: Any) -> Optional[Path]:
    # frontmatter (single source of truth) > sm.project_root > sm.workdir
    fm = _read_frontmatter_project_root(sm)
    if fm is not None:
        return fm
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


# ---------- id helpers (mirror codemap_aimemory.knowledge_ids, stdlib-only) ----------

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _kebab(text: str) -> str:
    slug = _NON_SLUG.sub("-", (text or "").lower()).strip("-")
    return slug or hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]


def _case_id(spec_id: str) -> str:
    slug = _kebab(spec_id)
    return slug if slug.startswith("case-") else f"case-{slug}"


def _pit_knowledge_id(sig: str) -> str:
    slug = _kebab(sig)
    return slug if slug.startswith("pit-") else f"pit-{slug}"


# ---------- builders ----------


def _build_case_fields(
    spec_id: str, done_groups: list, run_dir: Path, sm: Any
) -> tuple[dict[str, Any], str]:
    """Aggregate all finished groups of a run into the semantic fields of one
    case (FIX-2). Returns ``(fields, md_body)`` — the writer stamps identity /
    schema / dates / version on top of ``fields``."""
    changed_files: list[str] = []
    key_decisions: list[dict[str, str]] = []
    bugs_encountered: list[str] = []
    review_findings: list[dict[str, str]] = []
    summary_parts: list[str] = []
    group_ids: list[str] = []
    titles: list[str] = []
    verdicts: list[str] = []

    for gs in done_groups:
        group_ids.append(gs.id)
        if gs.name:
            titles.append(gs.name)
        coder_results = _load_coder_results(run_dir, gs)
        review = _load_review(run_dir, gs)
        validations = _load_validations(run_dir, gs)

        for item in gs.items:
            for w in item.get("writes", []) or []:
                if w not in changed_files:
                    changed_files.append(w)

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

        if review is not None:
            for finding in review.p0_items:
                review_findings.append(
                    {"finding": finding.text[:240], "severity": "p0", "action": "addressed"}
                )
            for finding in review.p1_items:
                review_findings.append(
                    {"finding": finding.text[:240], "severity": "p1", "action": "addressed"}
                )

        part = _summarize_implementation(coder_results, gs)
        if part:
            summary_parts.append(part)
        if validations:
            verdicts.append(validations[-1].verdict)

    if verdicts and all(v == "pass" for v in verdicts):
        acceptance = "passed"
    elif any(v == "fail" for v in verdicts):
        acceptance = "failed"
    else:
        acceptance = "passed" if all(gs.status == "done" for gs in done_groups) else "partial"

    title = titles[0] if len(titles) == 1 else (spec_id or "case")
    implementation_summary = "\n".join(summary_parts)

    fields: dict[str, Any] = {
        "title": title,
        "group_ids": group_ids,
        "implementation_summary": implementation_summary,
        "changed_files": changed_files,
        "key_decisions": key_decisions,
        "bugs_encountered": bugs_encountered,
        "review_findings": review_findings,
        "acceptance_status": acceptance,
        "source_spec": sm.spec_dir or "",
        "source_files": ["requirements.md", "design.md", "implementation-log.md"],
        "related_code": [{"file": p} for p in changed_files],
        "tags": [],
        "confidence": "high" if acceptance == "passed" else "medium",
    }
    return fields, ""


def _inline_write_case(
    project_root: Path, payload: dict[str, Any], today: str
) -> dict[str, Any]:
    spec_id = payload.get("spec_id") or ""
    knowledge_id = _case_id(spec_id)
    cases_dir = project_root / ".ai-memory" / "knowledge" / "cases"
    yml_path = cases_dir / f"{knowledge_id}.yml"

    fields = dict(payload.get("fields") or {})
    confidence = fields.pop("confidence", None) or "high"
    fields.pop("status", None)

    existing = _load_yaml_if_exists(yml_path)
    if isinstance(existing, dict):
        version = (existing.get("version") if isinstance(existing.get("version"), int) else 1) + 1
        created_at = existing.get("created_at", today)
    else:
        version = 1
        created_at = today

    related = [spec_id] if spec_id else []
    kn: dict[str, Any] = {
        "schema_version": "1.0",
        "knowledge_id": knowledge_id,
        "type": "case",
        "case_id": knowledge_id,
        "spec_id": spec_id,
        "version": version,
        "created_at": created_at,
        "updated_at": today,
        "status": "active",
        "confidence": confidence,
        **fields,
        "related_requirements": related,
        "related_knowledge": [],
    }
    _dump_yaml(yml_path, kn)
    md_path = project_root / "knowledge-base" / "cases" / f"{knowledge_id}.md"
    _atomic_write_text(md_path, _case_to_md(kn))
    return {
        "knowledge_id": knowledge_id,
        "yml_path": str(yml_path),
        "md_path": str(md_path),
        "action": "superseded" if version > 1 else "created",
        "errors": [],
    }


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


def _extract_pit_parts(validation: ValidatorValidation) -> tuple[str, str, list[str], list[str]]:
    """Pull (title, symptom, fix_steps, affects) out of a validator fail."""
    title = _extract_pit_title(validation.failure_excerpt)
    symptom = (validation.failure_excerpt or "").strip()[:1000]
    fix_steps: list[str] = []
    affects: list[str] = []
    for tgt in validation.fix_targets or []:
        if tgt.suggestion:
            fix_steps.append(tgt.suggestion.strip())
        if tgt.file_path and tgt.file_path not in affects:
            affects.append(tgt.file_path)
    return title, symptom, fix_steps, affects


def _build_pit_fields(validation: ValidatorValidation, spec_id: str) -> dict[str, Any]:
    """Semantic fields of a pitfall (FIX-2). The writer stamps identity /
    dates / version and merges ``seen_again_in`` on repeats."""
    title, symptom, fix_steps, affects = _extract_pit_parts(validation)
    return {
        "title": (title or "")[:200],
        "symptom": symptom,
        "fix": fix_steps,
        "affects": affects,
        "first_seen_in": spec_id,
        "tags": ["validator-fail"],
        "confidence": "medium",
    }


def _inline_write_pitfall(
    project_root: Path, payload: dict[str, Any], today: str
) -> dict[str, Any]:
    sig = payload.get("signature") or ""
    spec_id = payload.get("spec_id") or ""
    knowledge_id = _pit_knowledge_id(sig)
    pit_path = project_root / ".ai-memory" / "knowledge" / "pitfalls" / f"{knowledge_id}.yml"
    fields = dict(payload.get("fields") or {})
    incoming_affects = list(fields.get("affects") or [])
    incoming_fix = list(fields.get("fix") or [])

    existing = _load_yaml_if_exists(pit_path)
    if isinstance(existing, dict):
        seen_again = list(existing.get("seen_again_in") or [])
        if spec_id and spec_id != existing.get("first_seen_in") and spec_id not in seen_again:
            seen_again.append(spec_id)
        merged_affects = list(existing.get("affects") or [])
        for a in incoming_affects:
            if a not in merged_affects:
                merged_affects.append(a)
        merged_fix = list(existing.get("fix") or [])
        for f in incoming_fix:
            if f not in merged_fix:
                merged_fix.append(f)
        version = (existing.get("version") if isinstance(existing.get("version"), int) else 1) + 1
        existing.update(
            {
                "updated_at": today,
                "version": version,
                "seen_again_in": seen_again,
                "affects": merged_affects,
                "fix": merged_fix,
            }
        )
        existing.setdefault("schema_version", "1.0")
        existing.setdefault("type", "pitfall")
        existing["knowledge_id"] = knowledge_id
        existing.setdefault("pit_id", knowledge_id)
        existing.setdefault("status", "active")
        existing.setdefault("confidence", "medium")
        kn = existing
        action = "merged"
    else:
        kn = {
            "schema_version": "1.0",
            "knowledge_id": knowledge_id,
            "type": "pitfall",
            "pit_id": knowledge_id,
            "version": 1,
            "title": fields.get("title") or knowledge_id,
            "symptom": fields.get("symptom", ""),
            "fix": incoming_fix,
            "affects": incoming_affects,
            "first_seen_in": spec_id,
            "seen_again_in": [],
            "tags": fields.get("tags") or ["validator-fail"],
            "created_at": today,
            "updated_at": today,
            "status": "active",
            "confidence": fields.get("confidence") or "medium",
        }
        action = "created"

    _dump_yaml(pit_path, kn)
    md_path = project_root / "knowledge-base" / "pitfalls" / f"{knowledge_id}.md"
    _atomic_write_text(md_path, _pit_to_md(kn))
    return {
        "knowledge_id": knowledge_id,
        "yml_path": str(pit_path),
        "md_path": str(md_path),
        "action": action,
        "errors": [],
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
