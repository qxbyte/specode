---
name: query
description: Use when the user (or a workflow like specode) needs to retrieve from a project knowledge-base — multi-channel RAG recall returning pointer cards, supports multi-round multi-angle querying
---

# RagKit Query

对项目 `knowledge-base/` 做多路召回（向量+词汇+元数据，RRF 融合），返回**定位卡片**。

## 执行

```sh
sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT}/scripts/ragkit.py" \
   query '<检索词>' --kb <项目根>/knowledge-base
```

- 检索词由你根据用户问题/需求**自行提炼**：优先用页面名、字段名、接口路径、功能域词。
- **允许多轮、多角度**：一轮不够就换角度再查（按页面查 / 按字段查 / 按调用链查），直到定位充分或确认无相关知识。
- 需要程序化消费时加 `--json`；`--top N` 调数量。

## 结果使用纪律（硬约束）

1. 卡片是**定位指针，非事实来源**——命中后用「路径」`Read` 原文，再跳到真实代码验证；禁止仅凭卡片摘要下结论。
2. tag/词面命中 ≠ 语义相关：逐条判断该知识点的改动类型/语义是否真适用，不适用就丢弃。
3. 独立 RAG 用法（用户直接提问系统历史逻辑）：召回 → Read 命中文档 → 综合整理回答，并注明来源文档路径。

## 降级与错误（stderr 信号，固定文案）

- `无可用向量后端`：结果仍有效（词汇+元数据路）；stderr 会带一个 ╭─ RagKit ─╮ 提示块，**原样转述给用户**（不改写、不省略）。
- `索引不存在`：提示用户先跑 `/ragkit:embed`。
- `model_mismatch` / `index_stale`：提示用户重跑 `/ragkit:embed`（必要时 `--rebuild`）。
