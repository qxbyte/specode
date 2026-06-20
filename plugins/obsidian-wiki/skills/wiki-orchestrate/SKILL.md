---
name: wiki-orchestrate
description: >
  整理 Obsidian LLM Wiki 的统一编排入口——定位 vault → 三方只读体检 →
  汇总行动计划 → 用户确认 → 按「结构→沉淀→策展」编排调用 wiki-struct、
  spec-distill、wiki-curate 完成整理。下一步该跑哪个 skill / 命令 / 参数由
  模型依据体检结果判断（建议性，非规则）。触发语：/wiki-orchestrate、
  /wiki-orchestrate scan、/wiki-orchestrate set-vault、「整理笔记库」、
  「跑一次编排」、「统一整理 vault」。入口自身不直接改内容笔记，所有写操作
  委托给子 skill 并继承其红线。
---

# wiki-orchestrate

整理笔记库的**统一入口**。把"逐步手动判断该调哪个 skill"换成一个
**模型驱动的编排 playbook**：先做只读体检，再让模型依据结果决定调用
`wiki-struct` / `spec-distill` / `wiki-curate` 的哪个命令、什么参数，
按序完成整理。本入口为后期"定时启动器"铺路（定时器不在本 skill 范围）。

完整设计见 DESIGN.md。

---

## 这是一篇 playbook，不是斜杠命令调度器

三个子 skill 当前**未注册为可 `/` 调用的命令**，它们由"确定性 Python 脚本 +
LLM 驱动的 SKILL.md 流程"两部分组成。本入口因此这样执行：

- **确定性部分**：直接 `python3` 运行子脚本（`struct_gen.py`、`kn_scan.py`）。
- **LLM 流程部分**：**内联读取**对应子 SKILL.md，按其步骤执行（拆知识点、写文档、
  问用户等）；子 skill 自身的确认关卡与红线照常生效。
- **编排部分**：本文件 + `references/` 告诉你——现在该读哪个子 SKILL.md、跑哪个
  脚本、传什么参数、依据什么体检信号判断下一步。

---

## 命令

| 命令 | 行为 |
|---|---|
| `/wiki-orchestrate`（= `run`） | 定位 vault → 三方只读体检 → 写 orchestrate-report → 呈现行动计划 → 用户批准后逐阶段执行 |
| `/wiki-orchestrate scan` | 只定位 + 三方只读体检 + 写 orchestrate-report，**不执行任何写阶段** |
| `/wiki-orchestrate set-vault [<路径>]` | 强制重设 vault 路径并写回 `$VPATH`（用户配置目录，见第 0 步；不传则询问用户） |
| `/wiki-orchestrate help` | 显示本命令表与三个子 skill 概览 |

未给子命令时按 `run` 处理。

---

## 第 0 步：定位 vault（每个命令都先做）

> **本套件作为插件安装、代码不在 vault 内**，所以 vault 路径**只能**由配置 / 用户给，不能从脚本位置推断。
> 状态文件 `vault-path.json` **不能**写在插件目录（cache，更新即丢），统一落到用户配置目录 `$VPATH`：
> ```bash
> VPATH="${XDG_CONFIG_HOME:-$HOME/.config}/obsidian-wiki/vault-path.json"
> ```

1. 读 `$VPATH` 的 `path` 字段（不存在视为未配置）。
2. **校验**：路径存在，且命中标志物 `<index_dir>/`（默认 `00-Index/`，标志物即"该库的 index 目录"），且 `<path>/.wiki/config.json` 存在。
3. 命中 → **静默复用**，不打扰用户，直接进入后续步骤。
4. 缺失 / 失效 → AskUserQuestion 询问 vault 路径（无法再从脚本位置上溯推断）。推荐选项 = `$VPATH` 里上次记录的路径；用户给出后**再次校验**（标志物 + `.wiki/config.json`），通过才 `mkdir -p` 其父目录并写回 `$VPATH`。
5. vault 路径含 `/Volumes/` → 额外确认外置盘已挂载（如 `ls "<path>"` 可访问）；未挂载**报错停止**，不静默写到别处。
6. 缺 `<path>/.wiki/config.json` → 报错并提示：从插件根 `config.example.json`（`$WIKI/config.example.json`，`$WIKI` 见第 1 步）抄一份到 `<path>/.wiki/config.json` 再跑。

`$VPATH` 文件结构（运行时生成 / 更新；机器相关，不入库）：

```json
{
  "path": "/Volumes/External HD/Obsidian/Notes",
  "updated": "2026-06-20",
  "host": "macos-xueqiang"
}
```

> `host` 仅作记录。跨终端 / 移动目录导致路径不命中时，走第 4 步重问并覆盖。
> `set-vault` 命令则**无条件**走第 4 步重设（写回 `$VPATH`）。

---

## 第 1 步：只读体检（不写任何笔记）

先解析插件根 `$WIKI`（四个子 skill 脚本都在 `$WIKI/skills/<name>/scripts/` 下）：

```bash
WIKI="${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT:-}}"; [ -d "$WIKI/skills/wiki-orchestrate" ] || WIKI="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" "$HOME/.copilot/installed-plugins" -type d -path '*/obsidian-wiki/skills/wiki-orchestrate' 2>/dev/null | sort -V | tail -1 | sed 's:/skills/wiki-orchestrate$::')"
```

依次运行（`<vault>` = 第 0 步定位结果），三者皆只读（只写各自 `_system/` 报告）：

```bash
python3 "$WIKI/skills/wiki-struct/scripts/struct_gen.py" check --vault "<vault>"
python3 "$WIKI/skills/spec-distill/scripts/kn_scan.py" scan --vault "<vault>"
python3 "$WIKI/skills/wiki-curate/scripts/lint.py" lint --vault "<vault>"
```

- struct check 写 `00-Index/_system/struct-report.md`：结构漂移 / 缺 marker / 缺文件 / 坏链 计数。
- kn_scan 写 `00-Index/_system/spec-distill-report.md`：待沉淀项目 / 已覆盖需求号 / 系统 计数。
- lint 写 `00-Index/_system/lint-report.md`：缺「用途」段 / 重复 basename / 孤儿无反链 / frontmatter 缺字段 计数（**确定性内容体检**，比读旧 curate-report 可靠）。
- **收件箱积压**：另用 glob 数 `99-Inbox/`、`Clippings/` 下待整理文件（只读）。坏链/结构归 struct check，不在此处。

读三方报告，提取关键数字。脚本若不存在或报错 → 在汇总里标注该子 skill 不可用、其阶段
将跳过，并提示用户。

---

## 第 2 步：汇总行动计划 → 写 orchestrate-report

把三方体检结果合并写到 `00-Index/_system/orchestrate-report.md`，至少包含：

- **概览**：结构（漂移/坏链/缺marker）、沉淀（待沉淀项目数/系统数）、策展（孤儿/缺用途/收件箱）三组数字。
- **建议行动计划**：模型依据 `references/decision-guide.md` 的**建议**，列出本次建议执行的
  阶段、每阶段建议命令 + 参数、是否需用户确认、可跳过的空阶段。
- **建议执行顺序**：默认「结构 → 沉淀 → 策展」，模型可据体检调整或跳过。
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

按默认序「结构 → 沉淀 → 策展」执行，模型可据体检**跳过**空阶段。每个阶段：

1. **阶段检查点**：进入前给一行摘要（"接下来做 X，将调用 Y"），**等用户确认**。
2. **内联执行子 SKILL.md**：读对应子 skill 的 SKILL.md，按其步骤执行；子 skill 自身的
   AskUserQuestion 关卡、备份、红线**照常生效**。
3. **阶段小结**：给一行结果（"已 apply N 个结构文件 / 沉淀 N 篇 / 补 N 处用途"）。

各阶段对应（命令与边界详见 `references/sub-skills.md`，均为**建议**，模型按需调整）：

- **结构层** → `wiki-struct`：通常 `struct_gen.py check` 后，按需 `apply [--scope ...]`；
  缺 marker 先按其 SKILL.md 走 `init`。
- **知识沉淀** → `spec-distill`：`kn_scan.py scan` 后，按其 SKILL.md 的 6 步 sync 流程
  逐项目处理（选系统归属、拆知识点、写文档、更新 MEMORY）。`sync` 是 LLM 流程，**不是**
  脚本子命令。
- **策展收尾** → `wiki-curate`：内容向策展——`ingest`（收件箱归类）、`curate`（补「用途」、
  英文标签改中文、在正文补双链修复孤儿）、`lint`（跑 `lint.py lint` + LLM 判断过时/矛盾）。
  **注意：坏链与结构漂移归 wiki-struct，不归 wiki-curate lint。** 命令对你开放，是否调用由你按需判断，不写死。

---

## 第 5 步：收尾

- 回填 orchestrate-report 的「本次已执行」段（哪些阶段跑了、各自结果）。
- 向 `00-Index/_system/wiki-log.md` 追加一行：

```text
- YYYY-MM-DD HH:MM wiki-orchestrate run (结构: <动作>, 沉淀: <动作>, 策展: <动作>)
```

---

## 红线与约束

| 红线 | 说明 |
|---|---|
| 入口不直接改内容笔记 | 所有写操作委托给子 skill，并**继承子 skill 红线**：SpecIn 只读；`10-Work/` 只写 `知识库/` 口袋；敏感目录只路径级；wiki-struct 只改受管块 |
| 双层确认 | 阶段间检查点（本入口）+ 子 skill 内置 AskUserQuestion 关卡，二者都保留 |
| 改前必读 | 编辑任何 `.md` 前先 Read |
| 写后写日志 | 任何写动作所在回合 append `00-Index/_system/wiki-log.md` |
| 破坏性/批量前备份 | 由被调用的子 skill 各自负责（tar 到各自 backup 目录） |
| 外置盘检查 | vault 含 `/Volumes/` 时先确认挂载；失败报错停止 |
| 不联网 | 全程不外发 vault 内容 |

---

## 跨平台

- **代码（本插件）与数据（vault）解耦**：代码随插件安装在 plugin cache（`$WIKI`），vault 结构在 `<vault>/.wiki/config.json`，vault 根由 `$VPATH`/用户给。零位置、零结构硬编码。
- 子脚本 `struct_gen.py` / `kn_scan.py` / `lint.py` 用 Python 标准库、UTF-8、不依赖外部包；调用一律传 `--vault "<vault>"`（必填），脚本据此读 `<vault>/.wiki/config.json`。
- 别人安装 = `/plugin` 装 obsidian-wiki → 在自己 vault 写 `.wiki/config.json`（抄插件根 `config.example.json`）→ 跑，无需改代码。
- `spec-distill` 源目录探测候选由配置 `knowledge.spec_in_candidates` 给（默认 `SpecIn` 无则 `spec-in`），兼容不同库。

---

## 与其它 skill 的关系

- **编排入口**，与 `wiki-struct` / `spec-distill` /
  `wiki-curate` 同属本插件 `skills/`，**通过调用它们**（`$WIKI/skills/<name>/scripts/…` + 内联读子 SKILL.md）完成整理，自身不重复实现其功能。`$WIKI` = 插件根（第 1 步解析）。
- 三个子 skill 的能力、命令、红线、触发信号详见 `references/sub-skills.md`。
- 下一步该调用谁的判断建议详见 `references/decision-guide.md`（建议性，最终由模型裁量）。

---

## References

- `references/sub-skills.md` —— 三个子 skill 能力说明（权威：能干什么、怎么调、读写边界、红线、触发信号）
- `references/decision-guide.md` —— 启发式建议（体检信号 → 倾向调用哪个 skill/命令/参数；**非规则**）
