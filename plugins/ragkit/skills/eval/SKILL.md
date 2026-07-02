---
name: eval
description: Use when measuring or tuning RagKit retrieval accuracy — runs the golden evalset and reports recall@k / MRR per bucket
---

# RagKit Eval

```sh
sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT}/scripts/ragkit.py" \
   eval --kb <知识库路径> [--evalset <file>] [--channels lexical,metadata]
```

- `--channels lexical,metadata` = 无向量基线；与全通道对比即向量路增益。
- 任何检索参数调优（分词/权重/RRF）都必须先跑 eval 留对照数字。
