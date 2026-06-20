# obsidian-wiki

一套维护 Obsidian **LLM-Wiki** 的插件（Karpathy 方法论：Sources 只读 / Wiki 由 LLM 写 / Schema 规约）。
**代码通用、零结构硬编码**：每个库的结构外置到 `<vault>/.wiki/config.json`，数据留在 vault。

## 四个 skill

| skill | 职责 | 入口 |
|---|---|---|
| **wiki-struct** | 结构层：Home 总览树 / 各级 README / 分区页受管块的确定性再生成 | `/wiki-struct` |
| **spec-distill** | 知识沉淀：SpecIn 需求逐项目提炼成知识库 + 维护 MEMORY | `/spec-distill` |
| **wiki-curate** | 内容策展：ingest / curate / lint（写作规范 + 红线 doctrine） | `/wiki-curate` |
| **wiki-orchestrate** | 统一编排：只读体检 → 计划 → 按「结构→沉淀→策展」调用上面三个 | `/wiki-orchestrate` |

`lib/wikicommon.py` 是三脚本共享库；`config.example.json` 是各库结构配置的模板。

## 安装

```text
/plugin marketplace add qxbyte/pluginhub      # 或本地路径 /plugin marketplace add /Users/xueqiang/Git/pluginhub
/plugin install obsidian-wiki@pluginhub
```

Claude Code、Copilot CLI、CodeBuddy 都按各自的 `/plugin` 机制安装；skill 自动发现。
Codex CLI 无 SKILL.md 斜杠系统，见根 `AGENTS.md`（脚本照跑，LLM 流程内联读对应 SKILL.md）。

## 用前：给你的 vault 写配置

把 `config.example.json` 抄到 `<你的vault>/.wiki/config.json`，按你的目录名改：

- `index_dir` / `home_file` / `system_dir` / `skip_dirs`：索引目录、Home 文件、报告目录、遍历跳过目录。
- `structure.dirs[]`：每个一级目录的 `dir/emoji/desc/callout/readme/partition/sensitive`。
- `lint`：要「用途」段的目录、孤儿检查范围、frontmatter 必填字段、敏感目录、`purpose_heading`。
- `knowledge`：知识库路径、spec 源候选与默认子路径、MEMORY 文件名与「需求反向索引」小节名。

**工具不变量不进配置**（marker 语法、报告文件名、渲染/解析算法随工具，不随库）。

## 约定

- Python 3 标准库、UTF-8、零外部依赖；脚本 `--vault` 必填，缺 `.wiki/config.json` 报清晰错误。
- 不修改内容笔记原文；只写各自报告 / 受管块 / 知识库口袋（红线见各 `skills/<name>/SKILL.md`）。
- 跨平台：相对 vault 根操作，不硬编码绝对路径。编排状态写用户配置目录 `~/.config/obsidian-wiki/`，不写插件目录。
