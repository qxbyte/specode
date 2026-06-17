---
description: Entry point for the specode lightweight spec workflow. `/spec <requirement>` creates a new spec; `/spec continue <slug>` resumes one; `/spec list` lists all.
argument-hint: "<requirement> | continue <slug> | list"
---

# /spec — specode lightweight workflow

Dispatch on the first token of `$ARGUMENTS`. All CLI calls go through the run.sh wrapper with the absolute `$CLAUDE_PLUGIN_ROOT` (fallback `$CODEBUDDY_PLUGIN_ROOT`) path:
`sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/resolve_root.py" <verb> ...`

After activation, follow the orchestration logic in specode SKILL.md (each phase calls superpowers if available, native fallback otherwise; three fixed artifacts land under `<specsRoot>/<slug>/`).

## A. `/spec list`
1. Call `resolve_root.py get-root`:
   - exit 3 (not configured) → run §D first-time setup, then continue.
   - exit 0 → obtain `<specsRoot>`.
2. Call `resolve_root.py list-specs` to list slugs; for each slug, read its spec directory documents and infer the current phase per the SKILL.md "documents as state" rule, then display both. No specs found → prompt user with `/spec <requirement>`. **Do not resume.**

## B. `/spec continue <slug>`
1. slug is required; if missing → report error and suggest `/spec list` to find slugs.
2. `resolve_root.py get-root` (not configured → §D) → locate `<specsRoot>/<slug>/`; directory not found → report error and suggest `/spec list`.
3. Read the spec directory documents, infer phase per SKILL.md "documents as state" rule, and resume from that phase (see SKILL.md §resume).

## C. `/spec <requirement>` (new spec)
1. `resolve_root.py get-root` (not configured → §D) → `<specsRoot>`.
2. The host agent derives a kebab-case `<slug>` from the requirement; `mkdir -p <specsRoot>/<slug>/`.
3. `project_root = current terminal cwd` (do not ask; convention is that the user has already `cd`-ed to the project directory before starting the conversation).
4. Follow SKILL.md §pipeline: requirements (brainstorming/native) → design (writing-plans/native) → "execution mode" selector → execution → acceptance. Three fixed artifacts land under `<specsRoot>/<slug>/`.

## D. First-time setup (only when get-root exits 3)
Call `AskUserQuestion` to ask the user for their「文档管理目录」(absolute path, used verbatim as the specs root) → once provided, call `resolve_root.py set-root --root <path>` to persist it → subsequent sessions will not ask again.
