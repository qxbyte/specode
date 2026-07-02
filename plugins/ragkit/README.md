# ragkit

> 独立知识库 RAG 插件（Claude Code / CodeBuddy），同时作为 specode `distill` 的可选下游消费者。

**ragkit** 提供向量 + 词汇 + 元数据三路召回，RRF 融合后返回**定位卡片**。核心仅依赖 stdlib + numpy；向量路按需接入本地模型（via uv sidecar）或第三方 OpenAI 兼容 API，无后端时自动降级。

## 定位

- **独立 RAG**：脱离 specode 独立使用，直接对任意 `cases/*.md + navigation/*.md` 结构的知识库做检索。
- **specode 可选消费**：specode `distill` 产出的 `knowledge-base/` 目录即是 ragkit 的输入。安装 ragkit 并构建索引后，specode 会在 requirements / design 阶段的 Tier-0 RagKit gate 自动调用 `ragkit:query` 多路召回，注入知识点定位指针；未安装或未建索引时零成本跳过。
- **零重型依赖**：词汇 + 元数据路仅需 stdlib + numpy，`embed` 返回退出码 3 时仍可完整使用这两路；向量路按后端可用情况自动激活。

## 安装与依赖

### 推荐：uv（支持 PEP 723 内联脚本元数据）

ragkit 脚本头部声明了 PEP 723 内联依赖（`# dependencies = ["numpy"]`），可直接用 `uv run` 免安装虚拟环境：

```sh
# 词汇/元数据路 + 索引操作（只需 numpy）
uv run plugins/ragkit/scripts/ragkit.py embed --kb <知识库路径>
```

### 向量路：本地模型（推荐，离线可用、零费用）

安装约 1.2GB 的本地 embedding 模型（默认 `Qwen/Qwen3-Embedding-0.6B`）：

```sh
uv run plugins/ragkit/scripts/ragkit_local_embed.py install

# 国内网络请先设置镜像
export HF_ENDPOINT=https://hf-mirror.com
uv run plugins/ragkit/scripts/ragkit_local_embed.py install
```

### 向量路：第三方 API（OpenAI 兼容）

```sh
uv run plugins/ragkit/scripts/ragkit.py backend set \
    --provider qwen --kb <知识库路径>
export DASHSCOPE_API_KEY=<你的密钥>
```

内置 preset（`--provider` 可选值）：

| preset | model | key_env |
| --- | --- | --- |
| `openai` | text-embedding-3-small | `OPENAI_API_KEY` |
| `qwen` | text-embedding-v4 | `DASHSCOPE_API_KEY` |
| `zhipu` | embedding-3 | `ZHIPUAI_API_KEY` |
| `voyage` | voyage-3 | `VOYAGE_API_KEY` |
| `azure` | text-embedding-3-small | `AZURE_OPENAI_API_KEY` |

自定义端点：`--base-url <url> --model <model> --key-env <ENV_VAR>`（任何 OpenAI 兼容接口均可）。

密钥只通过环境变量传入，**不落盘**。

### 无 uv 时的回退

仅需 numpy，可用系统/项目虚拟环境回退：

```sh
pip install numpy
python plugins/ragkit/scripts/ragkit.py embed --kb <知识库路径>
```

注意：无 uv 时本地模型路不可用（sidecar 需 `uv run`）；向量路请改用第三方 API。

## 命令用法

### embed — 构建/增量更新索引

```sh
uv run plugins/ragkit/scripts/ragkit.py embed --kb <知识库路径> [--rebuild]
```

- 默认**增量**：只重嵌变更 chunk；模型/后端切换或索引损坏时加 `--rebuild` 全量重建。
- 索引写入 `<知识库路径>/.ragkit/`；`knowledge-base/.gitignore` 应包含 `.ragkit/`（embed 自动写入）。
- **退出码 3** = 无向量后端：词汇 + 元数据索引已建好，`query` 可降级使用；stderr 的 ╭─ RagKit ─╮ 提示块**原样转述给用户**（不改写、不省略），含本地模型安装命令与第三方配置步骤。

**插件调用**（Claude Code / CodeBuddy）：

```
/ragkit:embed [--rebuild]
```

### query — 多路召回查询

```sh
uv run plugins/ragkit/scripts/ragkit.py query '<检索词>' \
    --kb <知识库路径> [--top N] [--channels lexical,metadata] [--json]
```

- 三路（向量 + 词汇 + 元数据）RRF 融合，返回定位卡片。
- `--channels lexical,metadata` 强制走词汇 + 元数据路（无向量基线场景）。
- `--json` 输出结构化 JSON，适合程序化消费；默认输出 Markdown 卡片。
- 卡片是**定位指针，非事实来源**——命中后用「路径」读原文再验证。

**插件调用**：

```
/ragkit:query <检索词>
```

### status — 索引健康检查

```sh
uv run plugins/ragkit/scripts/ragkit.py status \
    --kb <知识库路径> [--json]
```

关键字段解读：

| 字段 | 含义 |
| --- | --- |
| `n_docs_on_disk` | 磁盘上 cases/ + navigation/ 的 md 文件总数 |
| `n_docs_indexed` | 当前索引覆盖文档数 |
| `index_stale` | `true` = 有文档比索引新，建议重跑 embed |
| `drift.missing_from_index` | 磁盘有但索引没有的文档（需 embed 补录） |
| `backend_resolved` | 当前解析到的后端（`local` / `cloud` / `none`） |

**插件调用**：

```
/ragkit:status
```

### eval — 检索精度评测

```sh
uv run plugins/ragkit/scripts/ragkit.py eval \
    --kb <知识库路径> [--evalset <file>] [--top N] [--channels lexical,metadata] [--json]
```

- 默认读内置 `scripts/rag/evalset.json`（16 条 golden 问题，12 case + 4 navigation）。
- 输出：`recall@top`（top-N 召回率）和 `MRR`（平均倒数排名）整体 + 按 bucket 分项。
- `--channels lexical,metadata` = 无向量基线；与全通道（`lexical,metadata,vector`）对比即向量路增益。

**插件调用**：

```
/ragkit:eval [--channels lexical,metadata]
```

### backend — 后端配置管理

```sh
# 设置第三方 API preset
uv run plugins/ragkit/scripts/ragkit.py backend set \
    --provider qwen --kb <知识库路径>

# 查看当前配置
uv run plugins/ragkit/scripts/ragkit.py backend show --kb <知识库路径>

# 清除配置，回到自动解析
uv run plugins/ragkit/scripts/ragkit.py backend reset --kb <知识库路径>
```

## 后端解析优先级

固定优先级（由高到低）：

```
显式 cfg["backend"] > 本地模型已缓存 > 云端 API 已配置+密钥可读 > none（降级）
```

- **显式**：`backend.set` 写入 `.ragkit/config.json` 的 `backend` 字段，强制走指定路。
- **本地**：`~/.cache/huggingface/hub/models--<model>/snapshots/` 存在即视为已缓存。
- **云端**：`cloud.base_url` 非空且对应 `key_env` 环境变量已设置。
- **none**：三条均不满足时降级，embed 返回退出码 3，query 走词汇 + 元数据路。

**双后端并存时固定走本地**（本地优先于云端，无需手动选择）。

## 评测与调优

### 内置 golden 集

内置 16 条 golden 问题（`scripts/rag/evalset.json`，12 case + 4 navigation），覆盖
收付系统、加密任务、授权页面等典型检索场景。

扩充 golden 集方法：
1. 在 `evalset.json` 中追加 `{"query": "...", "expect": ["<knowledge_id>"], "bucket": "case|navigation"}` 条目。
2. `knowledge_id` 即 `cases/<name>.md` 或 `navigation/<name>.md` 的文件名（不含后缀）。
3. 跑 `eval` 查看新增条目的命中情况；MISS 列表给出 got 前三名，辅助调试。

### recall@5 / MRR 解读

| 指标 | 含义 | 目标 |
| --- | --- | --- |
| `recall@5` | 预期文档出现在 top-5 结果中的比例 | ≥0.85 为健康 |
| `MRR` | 平均倒数排名（越高越靠前） | ≥0.70 为健康 |

### 词汇基线对照用法

```sh
# 先跑词汇+元数据基线
uv run plugins/ragkit/scripts/ragkit.py eval \
    --kb <知识库路径> --channels lexical,metadata

# 配好向量后端并重跑 embed 后，对比全通道数字
uv run plugins/ragkit/scripts/ragkit.py eval \
    --kb <知识库路径>
```

两组数字之差即向量路的增益；调整分词权重或 RRF 参数前后均应留对照数字。

### 真实语料基线（本机 /Users/xueqiang/Git/knowledge-base，仅词汇+元数据路）

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

## 知识库目录结构

ragkit 只认以下结构（与 specode distill 产出格式一致）：

```
knowledge-base/
  cases/        ← 经验案例，每个 .md 对应一个知识点
  navigation/   ← 导航地图，指向代码位置
  MEMORY.md     ← 索引摘要（可选，给语言模型快速预览）
  .ragkit/      ← ragkit 索引目录（应加入 .gitignore）
    config.json
    chunks.json
    vectors.npy
    manifest.json
    model_id
```

## 与 specode 的集成

安装 ragkit 且 `knowledge-base/.ragkit/` 已构建后，specode 的 Tier-0 RagKit gate 自动生效：

1. 会话可用 skills 中存在 `ragkit:query`
2. `knowledge-base/.ragkit/` 目录存在

两个条件均满足时，specode requirements / design 阶段的经验检索自动切换为 `ragkit:query` 多路召回；否则零成本跳过。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 参数错误或知识库目录不存在 |
| 3 | embed 成功但无向量后端（词汇/元数据索引已建好） |
