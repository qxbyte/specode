# Karpathy LLM Wiki 方法论摘要

本文件浓缩 Andrej Karpathy 在 2026-04 发布的 LLM Wiki 方法论，作为 `wiki-curate` skill 的设计依据。

## 原始资料

- Karpathy 原始 gist：<https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
- 社区实践与扩展阅读：
  - Mehul Gupta, "Andrej Karpathy's LLM Knowledge Bases explained"（Medium, 2026-04）
  - Balu Kosuri, "I used Karpathy's LLM Wiki to build a knowledge base that maintains itself with AI"（Medium, 2026-04）
  - Victor, "Building an Andrej Karpathy–Style LLM Wiki for a Personal Knowledge Base"（Medium, 2026-05）
  - aimaker.substack.com, "How I Took Karpathy's LLM Wiki and Built an AI-Powered Second Brain in Obsidian"
  - MindStudio, "What Is Andrej Karpathy's LLM Wiki? How to Build a Personal Knowledge Base With Claude Code"

## 核心洞察

> **传统 RAG 的问题**：每次提问都从原始文档里检索片段、临时拼装答案。读得越多，记忆反而越散；每个新会话都从零开始。**没有任何东西在累积。**
>
> **LLM Wiki 的方案**：让 LLM 增量维护一个**结构化、持久、不断长大的 Markdown wiki**。每次新增材料、每次新提问，wiki 都变得更丰富。回答的不再是"片段拼接"，而是从已经精炼过的知识库里检索。

Karpathy 自己的一个主题在一段时间内长到了 **100 篇文章、40 万字**——比大多数博士论文还长，没有一个字是他亲手写的。

## 三层架构

| 层 | 内容 | 谁动 |
|---|---|---|
| **Raw sources** | 原始材料：文章、论文、图片、数据文件 | LLM 只读，绝不修改 |
| **The wiki** | LLM 生成的 markdown：摘要、实体页、概念页、对比页、综述 | LLM 增量写入和维护 |
| **The schema** | 约定文档（如 CLAUDE.md / 本 skill）：目录结构、命名规范、写作流程 | 人类制定，LLM 遵守 |

本 vault 的对应：

- **Raw sources（硬只读）**：`07-Ideas/`、`10-Work/`、`SpecIn/`
- **Raw sources（可归档）**：`99-Inbox/`、`Clippings/`（ingest 后用户确认可移动到 Wiki 区或归档）
- **Wiki**：`00-Index/`、`01-Concepts/`、`02-Models/`、`04-Tools/`、`05-Workflows/`、`06-Prompts/`、`08-Sources/`、`09-Journal/`
- **Schema**：`obsidian-wiki/{wiki-curate, wiki-struct}/` 及各自的 reference 文件

## 三类核心操作

### 1. Ingest（吸纳一篇新材料）

> "the LLM reads the source, discusses key takeaways with you, writes a summary page in the wiki, updates the index, updates relevant entity and concept pages, and appends an entry to the log."

具体落地见 `../SKILL.md` 的 Ingest 阶段。

### 2. Query（基于 Wiki 提问）

> "You ask questions against the wiki. The LLM searches for relevant pages, reads them, and synthesizes an answer with citations."

**不要全库 grep**。按索引链路检索：

1. 先读 `00-Index/Home.md`。
2. 根据问题选分类索引（`00-Index/01-Concepts.md`、`00-Index/04-Tools.md`、`00-Index/10-Work.md` 等）。
3. 如果分类索引指向项目索引（如 `10-Work/知识库/<子项目>/MEMORY.md`），先读项目索引。
4. 只读取回答所需的链接笔记。
5. 回答时说明依据来自哪些笔记。

### 3. Lint（健康检查）

> "Periodically, ask the LLM to health-check the wiki. Look for: contradictions between pages, stale claims, orphan pages, missing cross-references."

具体清单见 `lint-checklist.md`。

## 关键产物：Index 与 Log

### `index.md`（本 vault 对应 `00-Index/Home.md` + 11 个分类索引）

> "content-oriented. It's a catalog of everything in the wiki — each page listed with a link, a one-line summary, and optionally metadata."

不是裸文件列表，是**有摘要的目录**。每个条目要包含：

- 链接 `[[笔记]]`
- 一句话摘要
- 可选元数据：关键词、可以回答的问题、状态、来源

### `log.md`（本 vault 对应 `00-Index/_system/wiki-log.md`）

> "append-only record of what happened and when — ingests, queries, lint passes."

**只追加，不覆盖**。每次 ingest / curate / lint / 重要 query 记一行。格式：

```text
- 2026-06-05 00:42 ingest 99-Inbox/handbook.md -> 04-Tools/LLM Wiki 知识库工作原理.md (类型: 工作流)
- 2026-06-05 01:15 curate 在 01-Concepts/Redis高可用.md 正文补 [[01-Concepts/Redis的分布式架构]] 双链（孤儿修复）
- 2026-06-05 02:00 lint 缺用途 5 条、重复 basename 2 条、孤儿 3 条、frontmatter 缺字段 4 条（详见 lint-report.md）
- 2026-06-05 03:00 ingest 07-Ideas/CodeMap/README.md -> 01-Concepts/代码图谱.md (类型: 衍生，原文未动)
```

这条日志让未来的会话能恢复"上次进展到哪了"，是 LLM Wiki 跨会话的记忆延续。

## 实施哲学

> **You're in charge of sourcing, exploration, and asking the right questions. The LLM does all the grunt work — the summarizing, cross-referencing, filing, and bookkeeping.**

> The pattern works because **the tedious part of maintaining a knowledge base is not the reading or the thinking — it's the bookkeeping. LLMs don't get bored** and can update cross-references reliably across numerous files.

人类：选材、提问、判断方向。LLM：摘要、归类、补链、记账、健康检查。

## 与 Obsidian 的适配

Obsidian 是 IDE，LLM 是 programmer，wiki 是 codebase。

适配点：
- **双向链接**用 Obsidian wikilink `[[笔记]]` 或 `[[路径/笔记|显示名]]`。
- **图谱视图**可以直接观察 Wiki 的拓扑健康度（孤儿就是图里没有边连过来的节点）。
- **DB Folders 插件**（`Database/`）可作为高级元数据视图。
- **Excalidraw / Canvas** 可作为综述页的可视化补充。

**不要用 markdown link `[文本](路径.md)` 写内部链接**——会绕过 Obsidian 的反链系统，让孤儿/反链检测失真。

## 与本 skill 命令的对应

| Karpathy 概念 | 本 skill 命令 | 本 vault 产物 |
|---|---|---|
| Ingest | `/wiki-curate ingest <path>` | 新概念页 + 索引追加 + wiki-log 记录 |
| Query | （由用户直接提问，LLM 按本文 Query 流程检索） | 不在本 skill 命令路由内 |
| Lint | `/wiki-curate lint` | `00-Index/_system/lint-report.md` |
| index.md | （已有的）`00-Index/Home.md` + 11 个分类索引 | "有摘要的目录" |
| log.md | `/wiki-curate log` 查看 | `00-Index/_system/wiki-log.md`（append-only） |
| Schema | 本 skill 全套文件 | `obsidian-wiki/{wiki-curate, wiki-struct}/` |

## 本 vault 对原方法论的调整

| 原方法论 | 本 vault 调整 | 原因 |
|---|---|---|
| Sources 一律只读 | `99-Inbox/`、`Clippings/` 在 ingest 后**可**归档 | 这两个是"流转区"，留旧文件会让 scan 误报"待 ingest" |
| 同上 | `07-Ideas/`、`10-Work/`、`SpecIn/` 严格只读 | 项目笔记的自由形式有独立价值；工作资料含敏感字段；SpecIn 文档与 specode session 强绑定 |
| 一个 index.md | 一个 `Home.md` + 16 个目录（分区页/README 树由 wiki-struct 管） | vault 体量大，需要分类导航；结构层委托 wiki-struct |
| log 是普通文件 | log 放到 `00-Index/_system/` 与机器可读文件并列 | 与人类索引页分开，避免索引视图被日志噪音淹没 |
| Lint 是 LLM 体检 | Lint 分为脚本确定性项（缺用途/重复basename/孤儿/frontmatter）+ LLM 判断项（过时/矛盾对）；坏链/结构由 `/wiki-struct check` 负责 | 职责分离，内容健康与结构健康分开 |
