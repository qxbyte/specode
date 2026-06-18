---
description: List all specs under <specsRoot> with each one's inferred phase (for looking up slugs / overview; does not resume).
argument-hint: ""
---

# /specode:specode-list — list all specs

Resolve the plugin root + run.sh as in `/specode:specode-spec` (env var → cache-glob fallback):
```bash
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/specode/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/resolve_root.py" list-specs
```

1. `resolve_root.py get-root`: exit 3 (not configured) → first-time setup per SKILL.md §specsRoot, then continue; exit 0 → `<specsRoot>`.
2. `resolve_root.py list-specs` to list slugs; for each slug, read its spec directory documents and infer the current phase per the SKILL.md "documents as state" rule, then display both. No specs found → prompt user with `/specode:specode-spec <requirement>`. **Do not resume.**
