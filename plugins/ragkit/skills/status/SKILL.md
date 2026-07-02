---
name: status
description: Use when checking RagKit index health — doc/chunk counts, backend resolution, staleness and drift between knowledge-base and index
---

# RagKit Status

```sh
sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT}/scripts/ragkit.py" \
   status --kb <项目根>/knowledge-base --json
```

解读：`drift.missing_from_index` 非空或 `index_stale: true` → 建议重跑 embed；`backend_resolved: none` → 原样转述固定提示块。
