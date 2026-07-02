---
name: wiki-curate
description: 方法论伞 + ingest/curate/lint（内容向）——基于 Karpathy LLM Wiki 三层架构，对 vault 执行 Scan → Ingest → Curate → Lint 四阶段内容策展。结构层（Home 树/分区页/地图）见 wiki-struct；SpecIn 知识沉淀已迁移到 specode 的 /specode:distill（v2.0.0 剥离）。绝不修改只读目录原文（07-Ideas/、10-Work/、SpecIn/），不写 wiki-struct 受管块，不写遗留的 10-Work/知识库/ 产物。触发语：/wiki-curate、scan、ingest、curate、lint、「整理我的笔记库」、「整理 vault」、「整理 LLM Wiki」。
---


# Wiki Curate

> **配置说明**：vault 的结构配置存在**家目录注册表** `~/.config/obsidian-wiki/configs/<库名>.json`（按 active 库解析；未注册则回退库内 `<vault>/.wiki/config.json`）。schema 见本插件根 `config.example.json`。脚本仍通过 `--vault "<vault 根路径>"` 指定 vault，结构由注册表/回退提供。
>
> **脚本定位（插件）**：脚本随插件安装，运行前先解析插件根 `$WIKI`：
> ```bash
> WIKI="${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT:-}}"; [ -d "$WIKI/skills/wiki-curate" ] || WIKI="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" "$HOME/.copilot/installed-plugins" -type d -path '*/obsidian-wiki/skills/wiki-curate' 2>/dev/null | sort -V | tail -1 | sed 's:/skills/wiki-curate$::')"
> ```
> 下文命令里写的 `scripts/lint.py` 一律指 `"$WIKI/skills/wiki-curate/scripts/lint.py"`。

把目标 vault 长期维护成 Karpathy 风格的 LLM Wiki——**可累积、可检索、可双链浏览**的本地知识库。

## 设计依据

本 skill 基于 Andrej Karpathy 在 2026-04 发布的 LLM Wiki 方法论。核心思想：

- 不靠 RAG 反复检索原始材料，而是让 LLM 增量维护一个结构化、持久的 Markdown wiki。
- 三层架构：**Sources（只读）/ Wiki（LLM 写）/ Schema（规约）**。
- 三类操作：**Ingest（吸纳）/ Query（提问）/ Lint（健康检查）**。
- 关键产物：**index（带摘要的目录）** + **log（append-only 操作日志）**。
- 哲学：人选材+提问，LLM 摘要+归类+补链+记账+体检。

详细方法论与原文出处见 `references/karpathy-llm-wiki.md`。

## Vault 三层映射

| 层 | 当前 vault 中的目录 | 谁写 |
|---|---|---|
| **Raw sources（只读）** | `07-Ideas/`、`10-Work/`、`SpecIn/` | 用户写，**LLM 绝不修改** |
| **Raw sources（可归档）** | `99-Inbox/`、`Clippings/` | 用户放入，LLM ingest 后用户确认可移动 |
| **参考资料** | `03-Memo/`、`Database/`、`_scaffold/` | 用户维护，LLM 仅引用 |
| **Wiki** | `00-Index/`（结构归 wiki-struct）、`01-Concepts/`、`02-Models/`、`04-Tools/`、`05-Workflows/`、`06-Prompts/`、`08-Sources/`、`09-Journal/` | **LLM 增量写入与维护** |
| **Schema** | `obsidian-wiki/{wiki-curate, wiki-struct}/` | 人类制定 |

## 三条硬红线（必须遵守）

完整规则与边界情况见 `references/readonly-dirs-policy.md`。要点：

| 目录 | 永远不做 | 可以做 |
|---|---|---|
| `07-Ideas/` | mv / rm / rename / 重写正文 / 修 frontmatter | 在相关内容笔记正文补 `[[..]]` 双链；在 `01-Concepts/` 提炼通用概念 |
| `10-Work/` | mv / rm / rename / 复制敏感字段到 Wiki / 批量改 MEMORY.md | 提炼可公开概念到 `01-Concepts/`（按用户启动、逐个确认） |
| `SpecIn/` | mv / rm / rename / 改写 specode 工作流文档（requirements.md / design.md / tasks.md 等） | 在相关内容笔记补链接；知识沉淀交 specode 的 `/specode:distill` |

**敏感子目录更严格**：`10-Work/权限申请/`、`10-Work/系统/`、`99-Inbox/账号/`、`99-Inbox/激活/` 只做路径级索引（"账号/Docker.md - 容器镜像账号"这种粒度），不读取或摘要正文。

**不写 wiki-struct 受管块**：`00-Index/Home.md`、各一级目录 `README.md`、`00-Index/<目录>.md` 分区页的 `<!-- wiki-struct:tree ... -->` 块归 wiki-struct。ingest/curate 只改**内容笔记正文**（用途/标签/双链）和**文件归属目录**；结构由用户跑 `/wiki-struct apply` 自动收。

**不写遗留知识库产物**：`10-Work/知识库/<系统>/` 下的知识文档与 `MEMORY.md` 是已剥离的 spec-distill 的历史产物，保留只读；新沉淀走 specode 的 `/specode:distill`（写到各项目 `knowledge-base/`，不再写 vault）。

## 写作规范

完整规范见 `references/writing-conventions.md`。要点：

- **中文优先**：目录说明、笔记标题、标签、摘要、用途段一律中文。保留业界通用英文词（LLM、RAG、API、MCP、SDK、CLI、Claude Code、Obsidian 等）。
- **必含"用途"段**：`01-Concepts/` ~ `08-Sources/` 下每篇笔记都要有 `## 用途` 段，说明它解决什么问题、应该从哪些索引进入。
- **双链用 Obsidian wikilink**：`[[笔记]]` 或 `[[路径/笔记|显示名]]`。不要用 markdown link `[文本](路径.md)` 写内部链接——会绕过反链系统。
- **标签**：说明性标签中文（`概念`、`架构`、`日记`），命名空间标签可保留 `LLM/wiki`。
- **frontmatter 必填**：`类型`、`状态`、`标签`、`更新`。
- **来源外部链接**：用普通 markdown link 并注明访问日期。

模板见 `references/note-templates.md`。

## 触发命令路由

| 命令 | 行为 |
|---|---|
| `/wiki-curate` | 等价 `scan` |
| `/wiki-curate scan` | 内容健康侦察：跑 `python3 scripts/lint.py lint`（确定性检查）+ 列待 ingest 候选 + 最近新增，输出 `00-Index/_system/curate-report.md`；**结构/坏链见 `/wiki-struct check`** |
| `/wiki-curate ingest <path>` | 把指定一个或多个文件吸纳进 Wiki（写摘要/挂索引/补双链），通常指向 `99-Inbox/`、`Clippings/` 下一篇；完成后提示跑 `/wiki-struct apply` |
| `/wiki-curate ingest-all` | 批量 ingest 上述目录下的待办候选，逐篇向用户确认 |
| `/wiki-curate curate` | 内容策展：补缺失"用途"、改英文说明性标签为中文、在相关内容笔记正文补 `[[..]]` 修复孤儿双链；**不碰受管块** |
| `/wiki-curate lint` | 内容健康检查，跑 `python3 scripts/lint.py lint`（缺用途/重复 basename/孤儿/frontmatter 缺字段）+ LLM 判断过时/矛盾，输出 `00-Index/_system/lint-report.md`；坏链项见 `/wiki-struct check` |
| `/wiki-curate log` | 显示 `wiki-log.md` 最近 20 行操作记录 |
| `/wiki-curate help` | 显示本表格 |

未指定子命令时按 `scan` 处理，并向用户提议下一步。

spec 沉淀已迁移到 specode 插件的 `/specode:distill <slug>`（v2.0.0 剥离；写到各项目 `knowledge-base/`，不再写 vault）。

## 四阶段工作流

### Scan（侦察）

不动任何笔记，只产报告。

1. 跑 `python3 "$WIKI/skills/wiki-curate/scripts/lint.py" lint --vault "<vault>"`（确定性内容体检：缺"用途"段、重复 basename、孤儿无反链、frontmatter 缺字段）。
2. 列 **待 ingest**：`99-Inbox/`、`Clippings/` 下尚未在 `wiki-log.md` 留过 ingest 记录的文件。
3. 列 **最近新增**：mtime 在最近 N 天（默认 7 天）的 Wiki 区笔记。
4. 写报告到 `00-Index/_system/curate-report.md`，结构：概览 → 内容健康摘要 → 待 ingest → 最近新增 → 建议动作。
5. 结构漂移与坏链见 `/wiki-struct check`，本阶段不处理。
6. 向用户汇报概览数字 + 最值得动手的 3 件事，等指令再进下一阶段。

### Ingest（吸纳）

对**单篇**新材料按以下顺序：

1. **读源**：Read 完整读这篇笔记。
2. **判定类型**：概念 / 实体（模型、工具）/ 工作流 / 来源 / 日记 / 备忘。
3. **判定归属**：
   - 概念 → `01-Concepts/`
   - 模型 → `02-Models/`
   - 工具 → `04-Tools/`
   - 工作流 → `05-Workflows/`
   - 提示词 → `06-Prompts/`
   - 外部资料摘要 → `08-Sources/`
   - 日记 → `09-Journal/`
   - 备忘（敏感配置）→ `03-Memo/`
4. **决定动作**：
   - 全新主题 → 用 `references/note-templates.md` 模板新建笔记，写入内容笔记正文（用途/摘要/双链）。
   - 已有主页 → 追加一节，注明日期和来源链接。
   - 仅元数据级（如服务器备忘）→ 只在 `03-Memo/` 追加一行。
5. **放对 Wiki 目录**：把笔记写入判定好的 Wiki 目录；**不手改分区页**——分区页由 wiki-struct 受管块维护。
6. **补双链**：在新笔记或追加段落里加 `[[相关笔记]]`；如果相关笔记已存在，进入该笔记追加引回双链。
7. **记录日志**：append 一行到 `00-Index/_system/wiki-log.md`：
   ```text
   - YYYY-MM-DD HH:MM ingest <源路径> -> <wiki 路径> (类型: xxx)
   ```
8. **是否移动源文件**：
   - `99-Inbox/`、`Clippings/`：ingest 完成后，提示用户确认移动；用户批准后移动到 Wiki 目录或归档。
   - **`07-Ideas/`、`10-Work/`、`SpecIn/` 的文件：永远不移动**。
9. **提示结构更新**：完成后提示用户跑 `/wiki-struct apply` 让结构树自动收录新笔记。

### Curate（策展）

对**已有 Wiki 内容**做整理。

1. **补"用途"段**：扫描 `01-Concepts/` ~ `08-Sources/` 下缺失 `## 用途` 的笔记，按 vault 上下文补写并标记 `状态: 草稿`，让用户复核。
2. **统一标签**：英文说明性标签（`architecture`、`daily`）改为中文（`架构`、`日记`），保留 `LLM/wiki`。
3. **修复孤儿双链**：把 lint 报告里的孤儿逐篇找到**相关内容笔记正文**，在正文补 `[[孤儿笔记]]` 语义双链，**不是往分区索引加行**（分区索引是 wiki-struct 受管块）。
4. **不碰受管块**：`<!-- wiki-struct:tree ... -->` 块与分区页结构由 wiki-struct 维护；curate 绝不手动编辑这些部分。
5. **每次修改都写 log**：append 到 `wiki-log.md`。

### Lint（健康检查）

内容健康体检，专注内容笔记质量，不检查结构/坏链（见 `/wiki-struct check`）。

**确定性检查**（`python3 scripts/lint.py lint` 产出）：

1. **缺"用途"段**：警告级——`01-Concepts/` ~ `08-Sources/` 下缺 `## 用途` 的笔记。
2. **重复 basename**：警告级——全库（排除 `skills/`）同 basename 出现在多目录。
3. **孤儿（无反链）**：警告级——`01-Concepts/` ~ `08-Sources/` + `09-Journal/` 下从未被任何笔记引用的笔记。
4. **frontmatter 缺字段**：提示级——`01-Concepts/` ~ `08-Sources/` 下缺 `类型/状态/标签/更新` 任一字段。

**LLM 判断项**（lint-checklist.md 指导）：

5. **过时声明**：提示级——含具体版本号/价格/日期，且 `更新` 字段早于半年。
6. **矛盾对**：提示级——相同 H1，结论不同。

输出 `00-Index/_system/lint-report.md`，按类别分节。**坏链与结构漂移见 `/wiki-struct check`**，lint 不报这两项。

## 产物清单

本 skill 维护或创建的文件：

```text
00-Index/_system/
├── wiki-log.md                ← append-only 操作日志（ingest/curate/lint 均写入）
├── curate-report.md           ← scan 阶段产物
└── lint-report.md             ← lint 阶段产物（python3 scripts/lint.py lint 生成）
```

- **结构产物**（Home 树、分区页、README、地图）归 **wiki-struct**。
- **知识库产物**（`10-Work/知识库/<系统>/` 知识文档与 MEMORY.md）为**已剥离的 spec-distill 遗留产物**，保留只读、不再维护。

## 操作约束

- **改前必读**：编辑任何 `.md` 前先 Read。
- **写后必写日志**：任何创建/修改/移动笔记的动作都在同一回合 append `wiki-log.md`。
- **批量操作必备份**：超过 10 个文件的批量改写前，tar 备份到 `~/Library/Caches/wiki-curate-backup-<ts>/`。
- **优先用 Edit/Write 而不是 sed/mv**：vault 在外置盘、含中文路径与空格，文件操作要稳定可回溯；mv 涉及只读目录直接拒绝执行。
- **不联网**：不把 vault 内容发到外部 LLM、笔记同步、向量库；只用本机 Claude Code 上下文。
- **任何破坏性动作前 AskUserQuestion**：移动文件（仅限非只读目录）、删除孤儿页、合并重复笔记，必须列出来源与目标让用户批准。

## 与用户对话的节奏

- 每个阶段开始前用一句话说"我现在要做 X"，结束后给一行摘要。
- Scan 完成后汇报：(a) 概览数字，(b) 最值得动手的 3 件事，等指令再进 ingest/curate/lint。
- 每个 ingest 或 curate 动作前用一句话说"我要把 X 加到 Y、补 Z 链接"再动手。
- 不要默认进下一阶段；用户驱动节奏。

## 问答检索流程

当用户基于本地笔记提问时，不要全库 grep，按索引链路检索：

1. 先读 `00-Index/Home.md`，找到全局入口。
2. 根据问题选分类索引（如 `00-Index/01-Concepts.md`、`00-Index/04-Tools.md`、`00-Index/10-Work.md`）。
3. 如果分类索引指向项目索引（如 `10-Work/知识库/<子项目>/MEMORY.md`），先读项目索引，再读原始笔记。
4. 只读取回答所需的链接笔记。
5. 回答时说明关键依据来自哪些笔记。

## 参考文档（references/）

- `karpathy-llm-wiki.md`：方法论摘要、原文出处、术语与本 vault 的对应；三层映射含 wiki-struct 分工
- `writing-conventions.md`：完整写作规范——目录模型、笔记类型、标签、frontmatter、中文化原则；含"index/分区页/Home 由 wiki-struct 受管块维护，curate/ingest 不手改"的职责边界
- `note-templates.md`：索引/概念/实体/工作流/来源/日记的标准模板；spec 知识沉淀模板见 specode 插件 `skills/distill/references/doc-template.md`
- `readonly-dirs-policy.md`：三个只读目录（`07-Ideas/`、`10-Work/`、`SpecIn/`）的详细规则、敏感子目录处理、衍生页写作规则；`10-Work/知识库/` 为遗留产物、只读
- `lint-checklist.md`：Lint 阶段内容健康检查清单（对齐 `scripts/lint.py` 四项确定性检查 + LLM 判断项）；坏链与结构漂移见 `/wiki-struct check`
