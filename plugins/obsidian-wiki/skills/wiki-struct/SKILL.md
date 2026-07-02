---
name: wiki-struct
description: 维护 Obsidian LLM Wiki 的"结构层"——确定性重写 Home 总览树、各一级目录 README、00-Index 分区页的"受管块"，并产出结构体检报告。触发语：/wiki-struct、/wiki-struct check、/wiki-struct apply、/wiki-struct init、"刷新 Home 树"、"更新 README 目录"、"整理结构层"。绝不修改内容笔记原文，只重写 marker 包裹的受管块。
---

# Wiki Struct

> **配置说明**：vault 的结构配置存在**家目录注册表** `~/.config/obsidian-wiki/configs/<库名>.json`（按 active 库解析；未注册则回退库内 `<vault>/.wiki/config.json`）。schema 见本插件根 `config.example.json`。脚本仍通过 `--vault "<vault 根路径>"` 指定 vault，结构由注册表/回退提供。
>
> **脚本定位（插件）**：脚本随插件安装，运行前先解析插件根 `$WIKI`（一次设好，后续命令复用）：
> ```bash
> WIKI="${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT:-}}"; [ -d "$WIKI/skills/wiki-struct" ] || WIKI="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" "$HOME/.copilot/installed-plugins" -type d -path '*/obsidian-wiki/skills/wiki-struct' 2>/dev/null | sort -V | tail -1 | sed 's:/skills/wiki-struct$::')"
> ```
> 下文命令里写的 `scripts/struct_gen.py` 一律指 `"$WIKI/skills/wiki-struct/scripts/struct_gen.py"`。

把"结构层"从手工维护变成可重跑、确定性、内容安全的再生成。设计与约定见本插件根 `DESIGN.md`（位于 `skills/wiki-orchestrate/` 旁的套件文档）。

## 受管块

结构文件里自动内容放在 marker 之间，本 skill 只重写 marker 之间，marker 外人工内容一字不动：

```markdown
<!-- wiki-struct:tree start -->
…（自动生成的树 / 文件清单）…
<!-- wiki-struct:tree end -->
```

三类结构文件：`00-Index/Home.md`（全库 callout 树）、15 个一级目录 `README.md`（本目录文件清单）、15 个 `00-Index/<目录>.md` 分区页（本目录文档清单树）。详见 `references/managed-blocks.md`。

## 命令

| 命令 | 行为 |
|---|---|
| `/wiki-struct`（= check） | 跑 `python3 scripts/struct_gen.py check`，读 `00-Index/_system/struct-report.md`，汇报概览 + 最该处理项。不写结构文件 |
| `/wiki-struct apply [--scope home\|readmes\|partitions\|all]` | 备份 → `struct_gen.py apply` → 坏链复核 → 写 wiki-log。改前确认 |
| `/wiki-struct init` | 为缺 marker 的结构文件插入受管区（逐文件 AskUserQuestion 确认位置），见下 |
| `/wiki-struct help` | 显示本表 |

未给子命令按 check 处理。

## 执行流程

### check

1. 运行 `python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" check --vault "<vault>"`.
2. Read `00-Index/_system/struct-report.md`。
3. 汇报：需更新数 / 缺 marker 数 / 缺文件数 / 坏链数 + 最该处理的 3 项。等用户指令。

### init（首次接入，逐文件）

**原则：受管块只新插入、绝不包裹/替换人工策展清单。**

对报告里"缺 marker"的每个结构文件：

1. Read 该文件。判定两种情况：
   - **Home.md**：现有 `## 目录树` 下的 callout 树本就是上轮自动生成、无人工策展 → 可**就地包裹**这段（marker 包到 callout 树两端）。
   - **README / 分区页**：现有清单可能是人工策展的主题分组/项目表（如 `07-Ideas/README` 的项目表、`01-Concepts` 分区页的 `### 架构设计` 分组）→ **不碰它们**，改为**新插入**一个受管块小节 `## 目录树（自动维护）`，位置默认在文件末尾的"关联"段之前、或 `## 用途` 之后。
2. AskUserQuestion 逐文件确认：「就地包裹现有自动树（仅 Home）/ 在〈位置〉新插入受管块 / 跳过本文件」。
3. 用 Edit 插入 `<!-- wiki-struct:tree start -->` 空行 `<!-- wiki-struct:tree end -->`（新插入时块内先留空，由 apply 填充；就地包裹时不改段内内容）。
4. 全部插完后跑一次 `apply` 填充。

### apply

1. **先 check**：若仍有"缺 marker"文件，提示先 init，终止。
2. **备份**：`tar -czf ~/Library/Caches/wiki-struct-backup-<ts>.tgz` 受影响的结构文件。
3. 运行 `python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" apply [--scope ...] --vault "<vault>"`。
4. **坏链复核**：再跑一次 check，确认 broken 数未新增。
5. **写日志**：append 一行到 `00-Index/_system/wiki-log.md`：
   `- YYYY-MM-DD HH:MM wiki-struct apply (scope: <scope>, changed: <n>)`
6. 汇报改了哪些文件。

## 红线

- 只重写结构文件的受管块。**永不修改/移动/重命名任何内容笔记**（`07-Ideas/`、`10-Work/`、`SpecIn/`、`03-Memo/` 下除 README 外的 `.md` 都是内容笔记，不动）。
- 敏感目录（`03-Memo/`、`10-Work/权限申请·系统`、`99-Inbox/账号·激活`）受管块只含文件名级链接（生成器本就不读正文，天然满足）。
- 改前必读；apply/init 前 AskUserQuestion；写后写 wiki-log；apply 前 tar 备份。
- 外置盘未挂载（`ls "/Volumes/External HD"` 失败）→ 报错停。
- 不联网。

## 维护 skill 套件中的分工

本 skill 是**结构层**。同套件还有：`wiki-curate`（方法论伞 + 内容向 ingest/curate/lint + 写作规范/红线/模板 doctrine）、`wiki-orchestrate`（统一编排）。各管一摊：结构 → wiki-struct，内容策展与方法论 → wiki-curate。（spec-distill 知识沉淀已于 v2.0.0 剥离，迁往 specode 的 `/specode:distill`。）

## 参考

- `DESIGN.md`（套件根）：完整设计与验收标准
- `references/managed-blocks.md`：marker 语法、三类受管块定义、init 迁移规则
- `references/dir-config.md`：目录配置表、渲染规则、敏感目录、新增目录怎么改
