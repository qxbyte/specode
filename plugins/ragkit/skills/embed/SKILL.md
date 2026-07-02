---
name: embed
description: Use when building or refreshing the RagKit vector index for a project knowledge-base (after distill produced/updated knowledge points)
---

# RagKit Embed

```sh
sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT}/scripts/ragkit.py" \
   embed --kb <项目根>/knowledge-base
```

- 增量：默认只重嵌变更 chunk；模型/后端变更或索引损坏时加 `--rebuild`。
- **退出码 3** = 无向量后端：stdout 的 ╭─ RagKit ─╮ 提示块**必须原样转述给用户**（含安装命令与第三方配置方法，不要改写）；此时词汇/元数据索引已建好，query 可降级使用。
- 首次装本地模型：`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/ragkit_local_embed.py" install`（约 1.2GB；国内先 `export HF_ENDPOINT=https://hf-mirror.com`）。
- 双后端并存时固定用本地（脚本内置优先级，无需选择）。
