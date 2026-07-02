---
name: wiki-orchestrate
description: >
  整理 Obsidian LLM Wiki 的统一编排入口——定位 vault → 两方只读体检 →
  汇总行动计划 → 用户确认 → 按「结构→策展」编排调用 wiki-struct、
  wiki-curate 完成整理。下一步该跑哪个 skill / 命令 / 参数由
  模型依据体检结果判断（建议性，非规则）。触发语：/wiki-orchestrate、
  /wiki-orchestrate scan、/wiki-orchestrate set-vault、「整理笔记库」、
  「跑一次编排」、「统一整理 vault」。入口自身不直接改内容笔记，所有写操作
  委托给子 skill 并继承其红线。
---

# wiki-orchestrate

整理笔记库的**统一入口**。把"逐步手动判断该调哪个 skill"换成一个
**模型驱动的编排 playbook**：先做只读体检，再让模型依据结果决定调用
`wiki-struct` / `wiki-curate` 的哪个命令、什么参数，
按序完成整理。本入口为后期"定时启动器"铺路（定时器不在本 skill 范围）。

> spec-distill（知识沉淀阶段）已于 v2.0.0 剥离并迁移到 specode 的
> `/specode:distill`；本编排不再含「沉淀」阶段。

完整设计见 DESIGN.md。

---

## 这是一篇 playbook，不是斜杠命令调度器

两个子 skill 当前**未注册为可 `/` 调用的命令**，它们由"确定性 Python 脚本 +
LLM 驱动的 SKILL.md 流程"两部分组成。本入口因此这样执行：

- **确定性部分**：直接 `python3` 运行子脚本（`struct_gen.py`、`lint.py`）。
- **LLM 流程部分**：**内联读取**对应子 SKILL.md，按其步骤执行（拆知识点、写文档、
  问用户等）；子 skill 自身的确认关卡与红线照常生效。
- **编排部分**：本文件 + `references/` 告诉你——现在该读哪个子 SKILL.md、跑哪个
  脚本、传什么参数、依据什么体检信号判断下一步。

---

## 命令

| 命令 | 行为 |
|---|---|
| `/wiki-orchestrate`（= `run`） | 定位 vault → 两方只读体检 → 写 orchestrate-report → 呈现行动计划 → 用户批准后逐阶段执行 |
| `/wiki-orchestrate scan` | 只定位 + 两方只读体检 + 写 orchestrate-report，**不执行任何写阶段** |
| `/wiki-orchestrate set-vault [<路径>\|<名>]` | 重设/切换 active 库：已注册库用 `registry.py set-active --name <名>`，新库用 `register --activate`（见第 0 步）；不传则询问用户 |
| `/wiki-orchestrate help` | 显示本命令表与两个子 skill 概览 |

未给子命令时按 `run` 处理。

---

## 第 0 步：定位 vault（每个命令都先做）

> **本套件作为插件安装、代码不在 vault 内**；vault 路径与各库结构配置都登记在**家目录注册表** `~/.config/obsidian-wiki/`（`vaults.json` 存各库 path + active，`configs/<名>.json` 存各库结构）。**既不写插件目录**（cache，更新即丢）、**也不再写进 vault**。注册表读写统一走 `registry.py`。

先解析插件根 `$WIKI`（脚本与 `registry.py` 都在其下，后续步骤复用）：

```bash
WIKI="${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT:-}}"; [ -d "$WIKI/skills/wiki-orchestrate" ] || WIKI="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" "$HOME/.copilot/installed-plugins" -type d -path '*/obsidian-wiki/skills/wiki-orchestrate' 2>/dev/null | sort -V | tail -1 | sed 's:/skills/wiki-orchestrate$::')"
```

1. 解析 active 库：`python3 "$WIKI/lib/registry.py" resolve`。
   - 成功 → 输出 JSON `{name, path, config, config_exists}`；取 `path` 作 `<vault>`。
   - 退出码 **3**（未配置）→ 走第 4 步注册。
2. **校验**：`path` 存在、命中标志物 `<index_dir>/`（默认 `00-Index/`，即"该库的 index 目录"）、且 `config_exists=true`。
3. 命中 → **静默复用**，不打扰用户，直接进入后续步骤。
4. 未配置 / 失效 → AskUserQuestion 询问 vault 路径，注册并播种配置：
   ```bash
   python3 "$WIKI/lib/registry.py" register --name <短名> --path "<vault>" --activate --config-from "$WIKI/config.example.json"
   ```
   然后**提示用户按自己库的目录名编辑** `~/.config/obsidian-wiki/configs/<短名>.json`（模板即 config.example.json）。改完再次校验通过才继续。
5. vault 路径含 `/Volumes/` → 额外确认外置盘已挂载（如 `ls "<path>"` 可访问）；未挂载**报错停止**，不静默写到别处。
6. `config_exists=false`（已注册但缺配置）→ 报错并提示：把 `$WIKI/config.example.json` 抄到 `~/.config/obsidian-wiki/configs/<名>.json` 并按库改，再跑。

注册表结构（`registry.py` 维护；机器相关，不入库）：

```json
{
  "active": "notes",
  "vaults": { "notes": { "path": "/Volumes/External HD/Obsidian/Notes" } }
}
```

> 多库：`vaults` 可有多个条目，`active` 决定默认操作哪个；`registry.py list` 查看、`set-active --name <名>` 切换。
> 跨终端 / 移动目录导致 active 库路径不命中时，走第 4 步重问并 `register --activate` 覆盖。

---

## 第 1 步：只读体检（不写任何笔记）

复用第 0 步解析好的 `$WIKI`（子 skill 脚本都在 `$WIKI/skills/<name>/scripts/` 下）。
依次运行（`<vault>` = 第 0 步 `registry.py resolve` 得到的 `path`），两者皆只读（只写各自 `_system/` 报告）：

```bash
python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" check --vault "<vault>"
python3 "$WIKI/skills/wiki-curate/scripts/lint.py" lint --vault "<vault>"
```

- struct check 写 `00-Index/_system/struct-report.md`：结构漂移 / 缺 marker / 缺文件 / 坏链 计数。
- lint 写 `00-Index/_system/lint-report.md`：缺「用途」段 / 重复 basename / 孤儿无反链 / frontmatter 缺字段 计数（**确定性内容体检**，比读旧 curate-report 可靠）。
- **收件箱积压**：另用 glob 数 `99-Inbox/`、`Clippings/` 下待整理文件（只读）。坏链/结构归 struct check，不在此处。

读两方报告，提取关键数字。脚本若不存在或报错 → 在汇总里标注该子 skill 不可用、其阶段
将跳过，并提示用户。

---

## 第 2 步：汇总行动计划 → 写 orchestrate-report

把两方体检结果合并写到 `00-Index/_system/orchestrate-report.md`，至少包含：

- **概览**：结构（漂移/坏链/缺marker）、策展（孤儿/缺用途/收件箱）两组数字。
- **建议行动计划**：模型依据 `references/decision-guide.md` 的**建议**，列出本次建议执行的
  阶段、每阶段建议命令 + 参数、是否需用户确认、可跳过的空阶段。
- **建议执行顺序**：默认「结构 → 策展」，模型可据体检调整或跳过。
- **本次已执行**（run 结束时回填；scan 时留空）。

模型判断点（参 `decision-guide.md`，全部建议性）：哪些阶段跳过 / 执行、项目落哪个系统、
敏感内容是否纳入、坏链是改名导致还是真悬空。

---

## 第 3 步：呈现计划，等待批准

向用户用简短摘要呈现 orchestrate-report 的「建议行动计划」，等待批准。

- `scan` 命令到此为止：报告已写，不进入任何写阶段。
- `run` 命令：用户批准后进入第 4 步。

---

## 第 4 步：逐阶段执行（run）

按默认序「结构 → 策展」执行，模型可据体检**跳过**空阶段。每个阶段：

1. **阶段检查点**：进入前给一行摘要（"接下来做 X，将调用 Y"），**等用户确认**。
2. **内联执行子 SKILL.md**：读对应子 skill 的 SKILL.md，按其步骤执行；子 skill 自身的
   AskUserQuestion 关卡、备份、红线**照常生效**。
3. **阶段小结**：给一行结果（"已 apply N 个结构文件 / 补 N 处用途"）。

各阶段对应（命令与边界详见 `references/sub-skills.md`，均为**建议**，模型按需调整）：

- **结构层** → `wiki-struct`：通常 `struct_gen.py check` 后，按需 `apply [--scope ...]`；
  缺 marker 先按其 SKILL.md 走 `init`。
- **策展收尾** → `wiki-curate`：内容向策展——`ingest`（收件箱归类）、`curate`（补「用途」、
  英文标签改中文、在正文补双链修复孤儿）、`lint`（跑 `lint.py lint` + LLM 判断过时/矛盾）。
  **注意：坏链与结构漂移归 wiki-struct，不归 wiki-curate lint。** 命令对你开放，是否调用由你按需判断，不写死。

---

## 第 5 步：收尾

- 回填 orchestrate-report 的「本次已执行」段（哪些阶段跑了、各自结果）。
- 向 `00-Index/_system/wiki-log.md` 追加一行：

```text
- YYYY-MM-DD HH:MM wiki-orchestrate run (结构: <动作>, 策展: <动作>)
```

---

## 红线与约束

| 红线 | 说明 |
|---|---|
| 入口不直接改内容笔记 | 所有写操作委托给子 skill，并**继承子 skill 红线**：SpecIn 只读；`10-Work/` 只读（原 `知识库/` 写口袋属已剥离的 spec-distill）；敏感目录只路径级；wiki-struct 只改受管块 |
| 双层确认 | 阶段间检查点（本入口）+ 子 skill 内置 AskUserQuestion 关卡，二者都保留 |
| 改前必读 | 编辑任何 `.md` 前先 Read |
| 写后写日志 | 任何写动作所在回合 append `00-Index/_system/wiki-log.md` |
| 破坏性/批量前备份 | 由被调用的子 skill 各自负责（tar 到各自 backup 目录） |
| 外置盘检查 | vault 含 `/Volumes/` 时先确认挂载；失败报错停止 |
| 不联网 | 全程不外发 vault 内容 |

---

## 跨平台

- **代码（本插件）/ 配置（家目录）/ 数据（vault）三者解耦**：代码随插件装在 plugin cache（`$WIKI`），各库结构配置在家目录注册表 `~/.config/obsidian-wiki/configs/<名>.json`，vault 根由 `registry.py resolve` 给。零位置、零结构硬编码，库内不再有 `.wiki/`。
- 子脚本 `struct_gen.py` / `lint.py` 用 Python 标准库、UTF-8、不依赖外部包；调用一律传 `--vault "<vault>"`（必填），脚本经 `load_config` 按 vault 路径在注册表里取该库配置（未注册则回退库内 `<vault>/.wiki/config.json`）。
- 别人安装 = `/plugin` 装 obsidian-wiki → `registry.py register --name <名> --path <vault> --config-from config.example.json` → 按库改 `configs/<名>.json` → 跑，无需改代码。

---

## 与其它 skill 的关系

- **编排入口**，与 `wiki-struct` /
  `wiki-curate` 同属本插件 `skills/`，**通过调用它们**（`$WIKI/skills/<name>/scripts/…` + 内联读子 SKILL.md）完成整理，自身不重复实现其功能。`$WIKI` = 插件根（第 0 步解析）。
- 两个子 skill 的能力、命令、红线、触发信号详见 `references/sub-skills.md`。
- 下一步该调用谁的判断建议详见 `references/decision-guide.md`（建议性，最终由模型裁量）。

---

## References

- `references/sub-skills.md` —— 两个子 skill 能力说明（权威：能干什么、怎么调、读写边界、红线、触发信号）
- `references/decision-guide.md` —— 启发式建议（体检信号 → 倾向调用哪个 skill/命令/参数；**非规则**）
