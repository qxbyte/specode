# Changelog — ragkit

## 0.1.0 (2026-07-03) — 初版发布

### Added

- **插件骨架**：`.claude-plugin/plugin.json`（版本 0.1.0）、`scripts/run.sh`、测试脚手架、4 个命令入口（embed / query / status / eval）。
- **三路召回 + RRF 融合**（`scripts/rag/channels.py` + `fuse.py`）：向量通道（余弦相似度）、词汇通道（BM25 风格 TF-IDF）、元数据通道（标题/标签关键词匹配），RRF 融合后按知识点去重，返回带 `ranked_by` 来源标注的定位卡片。
- **增量 embed + 退出码 3 固定块**（`cmd_embed`）：默认仅重嵌变更 chunk（按 `text_hash` 比对）；无向量后端时返回退出码 3，stdout 输出 ╭─ RagKit ─╮ 固定提示块（含本地模型安装命令与第三方 API 配置步骤），词汇 + 元数据索引同步落盘可降级使用。
- **status 漂移检测**（`cmd_status`）：报告 `n_docs_on_disk` / `n_docs_indexed` / `n_chunks` / `backend_resolved` / `index_stale`，并列出 `drift.missing_from_index` 与 `drift.deleted_on_disk`，支持 `--json`。
- **eval harness + 16 条 golden 问题**（`cmd_eval` + `scripts/rag/evalset.json`）：12 条 case bucket（收付/加密/授权场景）+ 4 条 navigation bucket，输出整体 `recall@top` + `MRR` 及按 bucket 分项，MISS 列表辅助调试；`--channels` 支持词汇基线与全通道对比。
- **4 个 Claude Code 技能**（`skills/embed|query|status|eval/SKILL.md`）：斜杠命令 `/ragkit:embed` / `/ragkit:query` / `/ragkit:status` / `/ragkit:eval`，含退出码 3 固定块转述规则和降级指引。
- **specode Tier-0 RagKit gate**（见 specode CHANGELOG v5.1.x）：specode `retrieval.md` 新增 Tier-0 gate，检测到 `ragkit:query` skill + 已建索引时，requirements / design 的经验检索自动走多路召回；未安装 / 未建索引零成本跳过。
- **后端解析优先级**（`scripts/rag/backend.py`）：`显式 cfg > 本地模型已缓存 > 云端 API 已配置 > none`；5 个内置 preset（openai / qwen / zhipu / voyage / azure）；`uv run` sidecar（`ragkit_local_embed.py`）隔离 torch / sentence-transformers 重型依赖。
- **chunker**（`scripts/rag/chunker.py`）：按 H2/H3 切片，保留 frontmatter 元数据（category / title / description / source / tags）。
- **hermetic 测试套件**：41 个 pytest cases，全用 dummy 后端，无网络、无模型依赖。

### 验收数字（真实语料，仅词汇+元数据路）

语料：`/Users/xueqiang/Git/knowledge-base`（30 cases + 18 navigation = 48 文档，146 chunks）。

```
n=16  recall@5=0.9375  mrr=0.8125
  [case] n=12 recall=0.9167 mrr=0.8125
  [navigation] n=4 recall=1.0 mrr=0.8125
MISS: 按收付登记号查询授权的后端三步链路
      → got ['121659-premium-query-paymentno-dialog-chain',
              '123000-cod-authority-new-components',
              '123000-cod-authority-save-three-table-sync']
```

全通道（向量）验收数字待配置向量后端后补录（本机无 uv/模型缓存/API key）。
