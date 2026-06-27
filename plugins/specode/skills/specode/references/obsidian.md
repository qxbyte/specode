---
description: Use when resolving the spec document root directory, performing first-time directory setup, or listing specs with `/specode:specode-list` — specsRoot three-tier resolution and directory conventions.
---

# specsRoot resolution and directory conventions

## Root source: single storage, single access point

specsRoot (the user's document management directory) is **stored in exactly one place**: the `specsRoot` key in `~/.config/specode/config.json`. Every script and command that needs this directory fetches it via `resolve_root.py get-root` — that is the **only access point**; nothing else should read the config directly.

`get-root` resolution order:
1. `--root` flag / env `SPECODE_ROOT` (temporary override for power users; not persisted)
2. `specsRoot` in `~/.config/specode/config.json` (**normal source**, used in every session)
3. Not found (no config) → **script cannot resolve = model cannot resolve** → model calls `AskUserQuestion` to ask the user for their document management directory (absolute path) → `resolve_root.py set-root --root <abs>` **writes it directly to the config file above** → all subsequent sessions read from config and will not ask again.

CLI via run.sh: `resolve_root.py get-root` / `set-root --root P` / `list-specs` (for the question example, see `selectors.md` §First-time directory setup).

## Directory conventions
- The directory the user provides is used **verbatim** as the specs root; specode appends no internal sub-structure (the user may supply a fully qualified path such as `.../spec-in/<os>-<user>/specs`).
- Each spec = `<specsRoot>/<slug>/`, containing the fixed files `requirements.md` / `design.md` / `implementation-log.md`.
- `pipeline.yml` is generated only when delegating to task-swarm; it is not a fixed artifact.
- project_root = the project whose `.ai-memory/knowledge` a spec feeds. It is the **single join key** between a spec and its project, stored in **exactly one place** — the spec's `requirements.md` YAML frontmatter — and accessed only through `resolve_root.py {resolve,write,read}-project-root`. Default is `git rev-parse --show-toplevel` of cwd (fallback cwd), **confirmed once via `AskUserQuestion`**, then persisted to frontmatter by `write-project-root`. Every later phase/skill (distill, task-swarm, recall) reads it via `read-project-root` — never re-derive from cwd/workdir, never guess.

## Documents as state (phase inference)
| Directory state | Phase |
|---|---|
| No requirements.md | intake |
| requirements.md present, no design.md | design |
| design.md present, unchecked `- [ ]` tasks remain | 执行中 |
| All design.md tasks checked | 完成 |
