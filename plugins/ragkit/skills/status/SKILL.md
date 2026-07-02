---
name: status
user-invocable: false
description: Use when checking RagKit index health — doc/chunk counts, backend resolution, staleness and drift between knowledge-base and index
---

# RagKit Status

```sh
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/ragkit/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/ragkit.py" \
   status --kb <项目根>/knowledge-base --json
```

解读：`drift.missing_from_index` 非空或 `index_stale: true` → 建议重跑 embed；`backend_resolved: none` → 原样转述固定提示块。
