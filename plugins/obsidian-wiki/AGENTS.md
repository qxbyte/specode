# obsidian-wiki — agent guide

维护 Obsidian **LLM-Wiki** 的一套 skill。代码通用、**零结构硬编码**：每个库的目录结构外置到
`<vault>/.wiki/config.json`，脚本据此运行。数据留在 vault，代码随插件安装。

> **给 Claude Code / Copilot CLI / CodeBuddy**：四个 skill 在 `skills/` 下，宿主会自动发现，
> 直接用触发语（`/wiki-struct`、`/spec-distill`、`/wiki-curate`、`/wiki-orchestrate` 或「整理笔记库」）即可。
> 各 skill 的完整流程、红线见对应 `skills/<name>/SKILL.md`。
>
> **给 Codex CLI（无 SKILL.md 斜杠系统）**：本文件即入口。按下文直接调脚本；需要 LLM 流程
> （`sync` 沉淀、`curate` 策展、`init` 插 marker、编排）时，**读对应 `skills/<name>/SKILL.md` 内联执行其步骤**。

## 四个 skill

| skill | 职责 | 确定性脚本（只读体检 / 重写受管块） |
|---|---|---|
| `wiki-struct` | 结构层：Home 总览树 / 各级 README / 分区页的受管块再生成 | `skills/wiki-struct/scripts/struct_gen.py check\|apply` |
| `spec-distill` | 知识沉淀：SpecIn 需求文档逐项目提炼成知识库 + 维护 MEMORY | `skills/spec-distill/scripts/kn_scan.py scan` |
| `wiki-curate` | 内容策展：ingest / curate / lint（写作规范与红线） | `skills/wiki-curate/scripts/lint.py lint` |
| `wiki-orchestrate` | 统一编排：只读体检 → 计划 → 按「结构→沉淀→策展」调用上面三个 | 无脚本（playbook） |

`lib/wikicommon.py` 是三脚本共享库（脚本自带相对 import，无需配置）。

## 跑脚本

脚本是 Python 3 标准库、UTF-8、零外部依赖。**`--vault` 必填**，脚本据此读 `<vault>/.wiki/config.json`。
先把插件根解析成 `$WIKI`（脚本在 `$WIKI/skills/<name>/scripts/` 下）：

```bash
WIKI="${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT:-}}"; [ -d "$WIKI/skills/wiki-struct" ] || WIKI="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" "$HOME/.copilot/installed-plugins" -type d -path '*/obsidian-wiki/skills/wiki-struct' 2>/dev/null | sort -V | tail -1 | sed 's:/skills/wiki-struct$::')"

V="/path/to/your/vault"
python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" check --vault "$V"
python3 "$WIKI/skills/spec-distill/scripts/kn_scan.py"   scan  --vault "$V"
python3 "$WIKI/skills/wiki-curate/scripts/lint.py"       lint  --vault "$V"
```

三者皆只读，仅向 `<vault>/<system_dir>/`（默认 `00-Index/_system/`）写体检报告。

## 首次配置

vault 缺 `.wiki/config.json` 时，从插件根 `config.example.json` 抄一份到 `<vault>/.wiki/config.json`，
按你的目录名改（`index_dir` / `structure.dirs[]` / `lint` / `knowledge` 等）。

## 红线（所有 skill 共同遵守）

- 绝不修改 / 移动 / 重命名内容笔记原文；`wiki-struct` 只改 marker 包裹的受管块。
- SpecIn 只读；`10-Work/` 仅 `知识库/` 可写；敏感目录受管块只到文件名级。
- 破坏性 / 批量写前 tar 备份；写动作所在回合 append `<system_dir>/wiki-log.md`。
- 全程不外发 vault 内容。
