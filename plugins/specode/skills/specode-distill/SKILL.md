---
name: specode-distill
description: >
  Manually distill a single specode-managed spec into Obsidian-friendly
  markdown knowledge files. Default output: md-only, written to
  `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/`. Trigger
  ONLY via `/specode:specode-distill <slug>` — never auto-triggered by
  the main specode flow (v4.0.0+). No codemap recall, no .ai-memory yml,
  no auto-injection into future specs. Pure "human-curated wiki organizer
  for Obsidian".
---

# specode-distill — manual Obsidian knowledge organizer

## v4.0.0 breaking redesign

Previous v1-v3 specode-distill was a "knowledge ingest pipeline" that
wrote dual yml + md to `<project_root>/.ai-memory/knowledge/` for codemap
recall to consume in future specs. Round 1/2 baseline experiments
showed the memory-injection round-trip did not net save token (recall
段 in task.md was extra context cost ≥ saving in most cases). v4.0.0
deletes that pipeline.

**v4 positioning**: a **manual, on-demand** organizer that converts a
finished spec into clean Obsidian markdown for the user's wiki. No
machine-readable yml (unless explicitly asked). No silent injection
elsewhere.

---

## Trigger

```
/specode:specode-distill <slug> [--target-dir <abs-path>] [--format md|yml|both]
```

| Arg | Default | Meaning |
|---|---|---|
| `<slug>` | (required) | spec slug under `<specsRoot>/` |
| `--target-dir` | `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/` | output root (must be absolute; will be `mkdir -p` 'd) |
| `--format` | `md` | `md` = obsidian markdown only; `yml` = machine yml only (writes to `<target-dir>/yml/<category>/<id>.yml`); `both` = pair |

**Manual only**: there is no auto-trigger. specode v4.0.0 main flow's acceptance phase **does not prompt** the user to distill. The user runs this command whenever they want to update their Obsidian wiki from a finished spec.

---

## Inputs

| Source | What it provides |
|---|---|
| `<specsRoot>/<slug>/` | spec dir: `requirements.md` / `design.md` / `implementation-log.md` etc. |
| `<specsRoot>/<slug>/requirements.md` YAML frontmatter | optional `project_root` (used only for relative path resolution in narrative — distill **does NOT write into** `<project_root>/.ai-memory/` v4+) |

---

## Output structure

```
<target-dir>/<slug>/
├── rules/
│   ├── <kebab-title>.md
│   └── ...
├── business/
│   └── <kebab-title>.md
├── modules/
│   └── <kebab-title>.md
├── cases/
│   └── <slug>.md       (always exactly 1 per spec)
└── pitfalls/
    └── <signature-kebab>.md
```

Each `.md` has Obsidian-friendly frontmatter + sections + `[[wikilink]]` cross-refs:

```markdown
---
title: 优惠券与积分互斥
category: rules
spec_id: <slug>
created_at: 2026-06-29
tags: [coupon, promotion]
related: [[biz-checkout-flow]], [[pit-coupon-stack]]
---

# 优惠券与积分互斥

## 规则陈述
...

## 为什么
...

## 适用场景
...

## 反例 / 中招经验
...
```

For `--format yml` or `--format both`: also writes `<target-dir>/<slug>/yml/<category>/<id>.yml` via `codemap knowledge write` (requires `codemap-aimemory` independent install). If `codemap` CLI not found and user picked `yml` / `both`, **abort with error** (do not silently degrade — user explicitly asked for yml).

---

## Flow (4 steps; user controls cadence)

### Step 1 — parse args + resolve target dir

Parse `<slug>`, optional `--target-dir`, `--format`. Defaults applied. Validate:
- `<specsRoot>/<slug>/` exists with at least `requirements.md`
- `--target-dir` is absolute. If on `/Volumes/`, verify mounted (`ls "/Volumes/<name>"` succeeds; refuse if unmounted)
- `mkdir -p <target-dir>/<slug>/{rules,business,modules,cases,pitfalls}`

### Step 2 — read the full spec

`Read` every `.md` under `<specsRoot>/<slug>/` (depth ≤ 3). Typical: requirements / design / implementation-log / bugfix / acceptance-checklist / tasks. Hold in memory for step 3.

> **v4 NO RECALL**: do NOT call `codemap recall` or read `.ai-memory/knowledge/`. Distill is purely from the spec docs.

### Step 3 — `AskUserQuestion` propose breakdown (non-skippable)

Apply 5-dimension heuristics (`references/breakdown-heuristics.md`) to propose N candidates per category:

- `rules/` — global mechanism / constraint identified in the spec
- `business/` — end-to-end flow / UI feature
- `modules/` — table / call chain / API surface touched
- `cases/` — this spec's implementation (always exactly 1, id = `<slug>`)
- `pitfalls/` — reusable failure / fix lesson from spec's `bugfix.md` or review findings

Each candidate carries: `category` / `title` (中文) / `summary` (一行) / `tags`. `knowledge_id` is derived as `<prefix>-<kebab(title)>`.

`AskUserQuestion`: user can confirm / add / drop / rename / recategorize. After confirmation, list is locked → step 4.

### Step 4 — write each knowledge point as Obsidian md

For each confirmed candidate, the host agent **directly authors the md content** (no external CLI). Template:

```markdown
---
title: <title>
category: <category>
spec_id: <slug>
created_at: <YYYY-MM-DD>
tags: <[tag1, tag2, ...]>
related: <[[id1]], [[id2]], ...>   # optional cross-refs
---

# <title>

<one-line summary>

## <category-specific section 1>
...

## <category-specific section 2>
...
```

Category-specific section sets (see `references/doc-template.md` for full template):

- **rules**: `规则陈述` / `为什么` / `适用场景` / `例外` / `如何强制`
- **business**: `业务流程` / `触发条件` / `结束状态` / `关键步骤` / `UI 约束`
- **modules**: `范围` / `主要 entity` / `数据列` / `分片策略` / `调用链`
- **cases**: `实施摘要` / `关键决策` / `踩过的坑 / fix` / `验收结果` / `变更文件`
- **pitfalls**: `现象` / `根因` / `修复方法` / `预防措施` / `影响范围`

Write each `.md` to `<target-dir>/<slug>/<category>/<knowledge_id>.md`. Existing file → `Read` then ask user `overwrite / skip / merge`.

For `--format yml` or `both`: also pipe to `codemap knowledge write` (independent install required). Writer's `--project` flag points to `<target-dir>/<slug>/yml-store` (a tmp dir; distill v4 does NOT use the spec's `project_root` here).

---

## Red lines

| Red line | Note |
|---|---|
| Spec dir is read-only | Never modify anything under `<specsRoot>/<slug>/` |
| `--target-dir` is the SOLE write scope | Distill writes only under `<target-dir>/<slug>/`. Never writes to spec dir or to `<project_root>/.ai-memory/` |
| External-drive precheck | If `--target-dir` is under `/Volumes/`, verify mounted; refuse if not |
| No codemap recall | v4 explicitly does NOT call `codemap recall`. Distill is purely spec-content driven |
| No silent yml | yml only written if user `--format yml` or `--format both`; default is md-only |
| No injection elsewhere | Distill output is for the user's Obsidian wiki — it does NOT feed any future spec's `requirements.md`, does NOT feed any `task.md` to subagents |
| Read-before-overwrite | If target md exists, `Read` then ask user before overwriting |

---

## What v4 does NOT do (vs v3)

| Removed | Why |
|---|---|
| Auto-trigger from acceptance phase | v4 specode main flow has no distill prompt; user runs manually only |
| Pre-step P2-2 codemap recall reverse-check | v4 doesn't read `.ai-memory/` at all |
| Default dual yml + md write | Default is md-only; yml requires explicit `--format yml` / `both` |
| Default write to `<project_root>/.ai-memory/knowledge/` | v4 default writes to `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/` |
| Coordination with task-swarm's ingest_lessons | task-swarm v0.10.0+ removes ingest entirely; no coordination needed |
| Same-id merge across distill + auto-ingest | No auto-ingest exists in v4; manual `--format both` writes are user's responsibility |

If user wants the v3 behavior (auto-trigger + write to `.ai-memory/`), checkout `backup/specode-v3.4.0-task-swarm-v0.9.2` branch.

---

## Coordination

`<target-dir>/<slug>/` is **not** read by any other specode/task-swarm phase. It's purely the user's Obsidian wiki staging. Subsequent `/wiki-sort` (obsidian-wiki plugin) can organize it into the LLM Wiki structure.

`<project_root>/.ai-memory/knowledge/` (if it exists from old v3 ingest) is **not touched** by v4 distill. Users can leave it for `codemap recall` independent use, or delete it.

---

## References

- `references/breakdown-heuristics.md` — 5-dimension breakdown → 5-category mapping
- `references/doc-template.md` — md template per category (5 templates total; yml templates retained for `--format yml` mode)
