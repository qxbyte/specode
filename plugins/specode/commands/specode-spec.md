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
3. `project_root` — the project whose `.ai-memory/knowledge` this spec feeds — is the **single source of truth** for every downstream consumer (specode-distill, task-swarm, codemap recall). Resolve it through the script, never re-derive from cwd ad hoc:
   - default: `resolve_root.py resolve-project-root` (returns `git rev-parse --show-toplevel` of cwd, falling back to cwd) → present it via `AskUserQuestion` **once** for the user to confirm/override.
   - persist: after requirements.md exists, `resolve_root.py write-project-root --spec <specsRoot>/<slug> --root <abs>` writes it into the requirements.md YAML frontmatter (validates absolute path / dir exists / `/Volumes` mounted). This frontmatter field is the **only** place project_root lives.
   - read (any later phase / skill): `resolve_root.py read-project-root --spec <specsRoot>/<slug>` — the single read entry. Never read cwd/workdir instead.
4. Follow SKILL.md §pipeline: requirements (brainstorming/native) → design (writing-plans/native) → "execution mode" selector → execution → acceptance. Three fixed artifacts land under `<specsRoot>/<slug>/`.
