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

## Outputs (dual: yml + md)

For each knowledge point identified by the LLM and confirmed by the
user (see §flow step 4), this skill writes **two parallel files** —
same content, different format:

```
<project_root>/
├── .ai-memory/knowledge/<category>/<knowledge_id>.yml   ← machine source
│   (consumed by codemap recall + future embedding indexer)
└── knowledge-base/<category>/<knowledge_id>.md          ← human + embedding source
    (Obsidian-friendly narrative; preserves prose / ascii flow charts /
     wikilinks that yml fields necessarily lose)
```

Categories (same in both directories):

| dir | id prefix | type | source heuristic |
|---|---|---|---|
| `rules/` | `rule-` | `business_rule` | global mechanism / constraint |
| `business/` | `biz-` | `business_process` | end-to-end flow / UI feature page |
| `modules/` | `mod-` | `module_map` | table / field / call chain / API surface |
| `cases/` | `case-` | `case` | this spec's implementation (always 1 per spec) |
| `pitfalls/` | `pit-` | `pitfall` | reusable failure / fix lesson |

See `references/doc-template.md` for both schema templates and md
templates per category.

---

## Flow (5 steps; user controls cadence)

### Step 1 — Resolve `project_root`

Priority (first non-empty wins):

1. CLI / argument `--project <abs>` (override; rare)
2. `<specsRoot>/<slug>/requirements.md` YAML frontmatter `project_root` field
3. **error: refuse to proceed**. Do not guess. Print one line:
   > `requirements.md` 缺 `project_root` frontmatter；specode v2.0 之前生成的 spec 需先手动补字段后重试。

Validate: path is absolute and the directory exists; else error and stop.

### Step 2 — Prepare target directories

```bash
mkdir -p "<project_root>/.ai-memory/knowledge/"{rules,business,modules,cases,pitfalls}
mkdir -p "<project_root>/knowledge-base/"{rules,business,modules,cases,pitfalls}
```

Existing files are not touched at this step — the per-knowledge merge
rule in step 5 handles same-id collisions.

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
- `knowledge_id` — `<prefix>-<kebab-slug>` matching the category
- `title` (Chinese) and a one-line summary
- `tags` (best-effort)
- `related_knowledge` — pre-fill with any recall hits judged relevant

Always include at least one `cases/case-<slug>-implementation.yml`
candidate (records this spec's implementation; source:
`implementation-log.md` + `bugfix.md` + `acceptance-checklist.md`).

Use `AskUserQuestion` to let the user **confirm / add / drop / rename
/ recategorize**. Never auto-skip this confirmation. After confirmation,
proceed to step 5 with the locked list.

### Step 5 — Write yml + md per knowledge point

For each confirmed knowledge point:

1. Render the **yml** per `references/doc-template.md` schema for its
   category. Write atomically to
   `<project_root>/.ai-memory/knowledge/<category>/<knowledge_id>.yml`.
2. Render the **md** per `references/doc-template.md` md template for
   its category. Write atomically to
   `<project_root>/knowledge-base/<category>/<knowledge_id>.md`.

**Same-id collision rule** (applies to both files):

- `Read` the existing file first.
- For `cases/case-*`: this spec re-runs supersede the prior write
  (overwrite both yml + md; bump `version: 1` → `version: 2`).
- For `rules/business/modules/pitfalls`: append-only changes —
  `updated_at: today`, `version +1`, `related_requirements` append
  this spec's id, `seen_again_in` (pitfall only) append. Do **not**
  rewrite structural fields without `AskUserQuestion` confirmation.

Both files share identical `knowledge_id` and stem — yml and md are
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
