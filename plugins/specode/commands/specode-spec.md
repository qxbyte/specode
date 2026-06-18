---
description: Create a new spec — clarify requirements → design → execution-mode selector → execute → acceptance, producing the 3 fixed artifacts under <specsRoot>/<slug>/.
argument-hint: "<requirement>"
---

# /specode:specode-spec — create a new spec

`$ARGUMENTS` is the requirement text. All CLI calls go through the run.sh wrapper with an absolute plugin-root path. The host env var `$CLAUDE_PLUGIN_ROOT` (CodeBuddy: `$CODEBUDDY_PLUGIN_ROOT`) is **not** reliably set in skill-driven Bash calls, so resolve the root robustly and fall back to a cache glob (newest version, never hard-coded). Prefix every CLI call with this self-contained resolver (shell state does not persist between Bash calls):
```bash
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/specode/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/resolve_root.py" <verb> ...
```
(`find` not a glob: zsh aborts on an unmatched glob; `find` stays silent.)

After activation, follow the orchestration logic in specode SKILL.md (each phase calls superpowers if available, native fallback otherwise; three fixed artifacts land under `<specsRoot>/<slug>/`).

1. `resolve_root.py get-root` (exit 3 / not configured → first-time setup per SKILL.md §specsRoot: `AskUserQuestion` for the document directory, then `set-root --root <abs>`) → `<specsRoot>`.
2. The host agent derives a kebab-case `<slug>` from the requirement; `mkdir -p <specsRoot>/<slug>/`.
3. `project_root = current terminal cwd` (do not ask; convention is that the user has already `cd`-ed to the project directory before starting the conversation).
4. Follow SKILL.md §pipeline: requirements (brainstorming/native) → design (writing-plans/native) → "execution mode" selector → execution → acceptance. Three fixed artifacts land under `<specsRoot>/<slug>/`.
