---
description: Resume an existing spec by slug — infers the current phase from which fixed docs exist + checkbox progress, and continues from there.
argument-hint: "<slug>"
---

# /specode:specode-continue — resume a spec

`$ARGUMENTS` is the spec slug (required). Resolve the plugin root + run.sh as in `/specode:specode-spec` (env var → cache-glob fallback):
```bash
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/specode/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/resolve_root.py" get-root
```

1. slug is required; if missing → report error and suggest `/specode:specode-list` to find slugs.
2. `resolve_root.py get-root` (not configured → first-time setup per SKILL.md §specsRoot) → locate `<specsRoot>/<slug>/`; directory not found → report error and suggest `/specode:specode-list`.
3. Read the spec directory documents, infer the phase per SKILL.md "documents as state" rule, and resume from that phase (see SKILL.md §resume).
