---
name: specode-distill
description: >
  Distill a single specode-managed spec into structured knowledge under
  the spec's own `project_root`: both machine-readable yml at
  `<project_root>/.ai-memory/knowledge/{rules,business,modules,cases,
  pitfalls}/*.yml` and human-readable + embedding-friendly markdown at
  `<project_root>/knowledge-base/{rules,business,modules,cases,
  pitfalls}/*.md`. Triggered automatically by specode's acceptance
  phase (with user opt-in) or manually via `/specode:specode-distill
  <slug>`. Strictly **per-spec** — never scans `<specsRoot>` globally,
  never writes outside the spec's own project.
---

# specode-distill — per-spec knowledge distillation

> **Why this skill is per-spec, not vault-wide**: each spec under
> `<specsRoot>` may target a different project (its absolute
> `project_root` is recorded in `requirements.md` frontmatter, written
> by specode v2.1+). Globally scanning `<specsRoot>` and writing
> knowledge to "one vault knowledge base" mixes specs from unrelated
> projects — exactly the bug the v1 spec-distill ran into. v3
> distills **one spec at a time** into its own `project_root`,
> eliminating the cross-project mix.

## When this skill runs

Two triggers (both end up calling the same flow):

1. **Auto-prompted (recommended)**: specode's main SKILL ends step 6
   (acceptance) by calling `AskUserQuestion` asking the user whether
   to distill this spec now. "Yes" → invoke this skill with the
   current slug. "No" → skip; the user can still trigger later.
2. **Manual**: `/specode:specode-distill <slug>` at any time, against
   any spec under `<specsRoot>` (typically a spec already accepted).

## Inputs

| Source | What it provides |
|---|---|
| `<specsRoot>/<slug>/` | The spec directory: `requirements.md` / `design.md` / `implementation-log.md` / `tasks.md` / `bugfix.md` / `acceptance-checklist.md` / test reports |
| `<specsRoot>/<slug>/requirements.md` YAML frontmatter | **`project_root`** (absolute path; written by specode v2.1+ at requirements-phase sub-step 2.1) |

## Outputs (dual: yml + md) — written by the single writer

For each knowledge point identified by the LLM and confirmed by the
user (see §flow step 4), this skill **does not hand-write files**. It
builds a *content payload* (semantic fields + an authored md body) and
invokes the single deterministic writer:

```
codemap knowledge write --project <project_root> --category <category> --payload -
```

The writer (codemap-aimemory ≥ 0.4.3) owns everything mechanical —
`knowledge_id` derivation, `schema_version` / `created_at` / `updated_at`
/ `version` stamping, schema validation, same-id merge, and the **atomic
dual write** of the twin files:

```
<project_root>/
├── .ai-memory/knowledge/<category>/<knowledge_id>.yml   ← machine source
│   (consumed by codemap recall + future embedding indexer)
└── knowledge-base/<category>/<knowledge_id>.md          ← human + embedding source
    (Obsidian-friendly narrative; the LLM-authored `md_body`, preserved
     verbatim — prose / ascii flow charts / wikilinks that yml fields lose)
```

> **Division of labour (方案A)**: the LLM owns *content* — which knowledge
> points exist, their category, each semantic field's value, and the md
> narrative body. Code owns *form* — id, schema, dates, paths, merge,
> validation. This is why the schema / id / merge logic lives in exactly
> one place (codemap-aimemory) instead of being re-described here.

Categories (same in both directories):

| dir | id prefix | type | source heuristic |
|---|---|---|---|
| `rules/` | `rule-` | `business_rule` | global mechanism / constraint |
| `business/` | `biz-` | `business_process` | end-to-end flow / UI feature page |
| `modules/` | `mod-` | `module_map` | table / field / call chain / API surface |
| `cases/` | `case-` | `case` | this spec's implementation (always 1 per spec) |
| `pitfalls/` | `pit-` | `pitfall` | reusable failure / fix lesson |

See `references/doc-template.md` for the per-category field set (what the
payload `fields` carry) and md body shape.

> **Fallback**: if `codemap knowledge write` is unavailable (codemap-aimemory
> not installed / too old), the host agent MAY hand-write the twin files per
> `references/doc-template.md` as a degraded mode — but the writer is the
> canonical path and should always be preferred.

---

## Flow (5 steps; user controls cadence)

### Step 1 — Resolve `project_root`

Use the **single read entry** — do not parse the frontmatter by hand, do not
guess from cwd:

```bash
resolve_root.py read-project-root --spec <specsRoot>/<slug>
```

Outcomes:

1. `--project <abs>` argument given (override; rare) → use it directly.
2. exit 0 → stdout is the validated absolute `project_root` (the verb already
   checked absolute path / dir exists / `/Volumes` mounted). Use it.
3. exit 3 (field missing) → **refuse to proceed**. Print one line:
   > `requirements.md` 缺 `project_root` frontmatter；specode v2.0 之前生成的 spec 需先手动补字段后重试（或重跑 specode requirements 阶段由 `write-project-root` 补写）。
4. exit 4 (value invalid: not absolute / dir missing / drive unmounted) → stop
   and surface the verb's stderr message; do not fall back to a guessed path.

> This is the same byte task-swarm reads for its ingest target, so the two
> channels can never diverge to different `.ai-memory/` (AI-EDS ISSUE-3).

### Step 2 — (no manual dir prep needed)

The writer (`codemap knowledge write`) creates
`<project_root>/.ai-memory/knowledge/<category>/` and
`<project_root>/knowledge-base/<category>/` on demand and handles same-id
collisions in step 5. Nothing to do here in the canonical path. (Only the
hand-write fallback needs `mkdir -p` — see step 5 fallback.)

### Step 3 — Read the full spec

`Read` every `.md` under `<specsRoot>/<slug>/` (depth ≤ 3): typically
`requirements`, `design`, `tasks`, `implementation-log`, `bugfix`,
`acceptance-checklist`, plus any test reports. Hold the contents in
memory for step 4.

### Step 4 — `AskUserQuestion` — propose breakdown (**non-skippable**)

**Pre-step (P2-2 — reverse-check existing pitfalls + rules)**: before
forming proposals, query the project's existing knowledge base for any
pitfalls / rules whose territory overlaps this spec. This prevents
proposing a *rule* that contradicts a known *pitfall*, and surfaces
historical context the LLM should weave into the new knowledge:

```bash
codemap recall --from-spec "<specsRoot>/<slug>/requirements.md" \
               --project "<project_root>" \
               --types rules,pitfalls \
               --top-k 5 \
               --output json
```

(Requires `codemap-aimemory>=0.3.6`. If `codemap recall` is unavailable,
silently skip the pre-step — proposals fall back to spec-only context.)

Parse the JSON; for each hit show the user a short bullet:
`- [[<knowledge_id>]] (<type>, score=<n>) — <title> · <summary>`. Do
NOT auto-merge the hits into proposals — they're context only. The
host agent uses them to:

1. Avoid proposing a `rule-*` whose `statement` directly conflicts
   with an existing `pit-*.symptom` (sanity check).
2. When proposing `case-*` / `pit-*` for this spec, link the existing
   ids into `related_knowledge` / `seen_again_in` where appropriate.

After the recall context is on screen, proceed with the breakdown
proposal proper:

Apply `references/breakdown-heuristics.md` (5 dimensions → 5
categories) to propose N knowledge candidates. Each candidate
**must** carry:

- `category` — `rules` / `business` / `modules` / `cases` / `pitfalls`
- `knowledge_id` — optional; the writer derives it (`<prefix>-<kebab>`) from
  `title` / `spec_id` / `signature` when omitted. Supply one only to pin it.
- `title` (Chinese) and a one-line summary
- `tags` (best-effort)
- `related_knowledge` — pre-fill with any recall hits judged relevant

Always include exactly one `cases` candidate for this spec — the writer
ids it `case-<spec_id>` (the **same** id task-swarm's auto-ingest uses, so
the human distill supersedes the auto case instead of duplicating it;
source: `implementation-log.md` + `bugfix.md` + `acceptance-checklist.md`).

Use `AskUserQuestion` to let the user **confirm / add / drop / rename
/ recategorize**. Never auto-skip this confirmation. After confirmation,
proceed to step 5 with the locked list.

### Step 5 — Write each knowledge point via the single writer

For each confirmed knowledge point, build a **content payload** and pipe it
to the writer (it owns id / schema / dates / version / merge / atomic dual
write — see §Outputs). Do **not** hand-render yml:

```bash
echo '<payload-json>' | codemap knowledge write \
    --project "<project_root>" --category <category> --payload - -o json
```

Payload shape (json):

```json
{
  "knowledge_id": "rule-coupon-mutex",   // optional — omit to let writer derive
  "spec_id": "<slug>",                    // case id + related_requirements
  "signature": "<sig>",                   // pitfalls only (→ pit-<sig>)
  "title": "优惠券与积分互斥",
  "fields": { "statement": "...", "why": "...", "...": "..." },
  "md_body": "## 一句话规则\n\n散文正文 + ascii + [[wikilink]] ...\n"
}
```

- `fields` carries the category's semantic fields (see
  `references/doc-template.md` for the per-category set). Do **not** put
  `schema_version` / `knowledge_id` / dates / `version` in `fields` — the
  writer stamps those.
- `md_body` is the **LLM-authored narrative** (方案A): prose, ascii flow
  charts, wikilinks. The writer writes it verbatim into the twin md under a
  machine-rendered frontmatter. Omit it only for trivially-structured
  knowledge (the writer then renders a minimal body from `fields`).
- Check the json result's `errors` (empty == ok) and `action`
  (`created` / `merged` / `superseded`).

**Same-id merge** is handled by the writer: `cases` supersede (overwrite +
`version` bump, `created_at` preserved); `rules` / `business` / `modules` /
`pitfalls` are append-only (structural fields preserved, `related_*`
appended, pitfalls' `seen_again_in` appended). If new info contradicts a
preserved structural field, surface it to the user via `AskUserQuestion`
(overwrite / new `-v2` id / skip) before forcing it.

**Fallback (writer unavailable)**: if `codemap knowledge write` is missing,
`mkdir -p` the two category dirs and hand-write the twin yml + md per
`references/doc-template.md`, applying the same merge rules manually. This is
a degraded path — prefer the writer.

Both files share an identical `knowledge_id` and stem — yml and md are
strictly twin views of the same knowledge.

---

## What this skill does **not** do

| Removed from v1/v2 spec-distill | Why |
|---|---|
| `scan` subcommand (vault-wide list-pending) | Per-spec model has no notion of "all pending across vault" |
| Vault `00-Index/_system/spec-distill-state.yml` | No global state needed; each spec writes to its own project |
| Vault `00-Index/_system/spec-distill-report.yml` | Same reason |
| Per-system grouping under `<vault>/10-Work/知识库/<系统>/` | Replaced by per-project `<project_root>/knowledge-base/` |
| MEMORY.md / wiki-log.md | Already dropped in v2 |
| `--vault <path>` flag | Doesn't apply — work targets are `<specsRoot>/<slug>/` and the spec's own `project_root` |
| Python helper script (`kn_scan.py`) | Pure LLM-driven flow; no script needed |

If a user previously relied on vault-wide scan to see "which specs
haven't been distilled," they can now run `ls <project_root>/.ai-memory/knowledge/cases/case-*.yml`
under each project they care about — each project's distillation
state is local and self-contained.

---

## Red lines (cannot be bypassed)

| Red line | Note |
|---|---|
| Spec dir is read-only | Never modify / move / rename anything under `<specsRoot>/<slug>/` |
| Writable scope: 2 dirs only | `<project_root>/.ai-memory/knowledge/` (yml) + `<project_root>/knowledge-base/` (md). Nothing else under `<project_root>` is touched |
| `project_root` MUST be in frontmatter | No guessing; refuse rather than write to the wrong project |
| Sensitive info gate | Account / token / key / personal-name+contact found in spec → `AskUserQuestion` listing positions; user decides include / redact / skip per item |
| Read-before-write on existing files | `Read` full content before overwriting any existing `.yml` or `.md` |
| External-drive precheck | If `project_root` lives under `/Volumes/`, verify `ls "/Volumes/<name>"` succeeds; refuse if unmounted (no silent fallback) |
| No network | This skill never reaches the network |

---

## Coordination with sibling channels

`<project_root>/.ai-memory/knowledge/` is also written by:

- **task-swarm 0.6+** `resolve` step: auto-writes `cases/case-<spec_id>-<gid>.yml` + `pitfalls/pit-<sig>.yml` + matching `.md` after every successful run.
- **codemap-aimemory 0.3+** emitter: writes peer dirs `.ai-memory/{project.yml, entities/, relations/, _global/}` — does NOT touch `knowledge/` (out of its scope).

This skill (`specode-distill`) adds the human-curated full 5-category
sweep that the auto channel (task-swarm) doesn't do. Same `id` from
two channels merges per step-5 collision rule; the auto channel's
machine-generated `case-*` typically gets superseded by the human-
curated one if the user chooses to re-distill the same spec manually.

---

## Cross-platform notes

- `project_root` MUST be an absolute path; validated against the host's path rules.
- All paths use forward slashes in yml/md content; the skill normalizes when actually writing on Windows.
- Pure LLM-driven; no Python or shell script dependency.

---

## References

- `references/breakdown-heuristics.md` — 5-dimension breakdown → 5-category mapping
- `references/doc-template.md` — both yml schema and md template per category (5 × 2 = 10 templates total)
