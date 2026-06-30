---
name: distill
user-invocable: false
description: >
  Manually distill a single specode-managed spec into atomic, locate-oriented
  markdown knowledge points. Default output: md-only, written to the project's
  own `<project_root>/knowledge-base/` (cases/ + navigation/ + MEMORY.md);
  optionally copied to an Obsidian vault. Trigger ONLY via
  `/specode:distill <slug>` — never auto-run by the main specode flow. No
  codemap recall, no .ai-memory yml, no auto-injection. Pure "atomic
  locate-pointer 沉淀器 for the current project".
---

# distill — project knowledge-base 沉淀器（原子双轨）

## 顶层不变量 🔒

**KB 是「定位用，非事实用」。** distill 写出的每个知识点是**定位指针**——
文件路径 + 调用链 + 可复用导航经验，**不是事实结论**。检索端只用它快速
**定位**到真实代码；真实代码始终是唯一事实来源。绝不允许仅凭 KB 内容推进
新需求，或把历史结论当成当前代码的真相。这条不变量是整套设计存在的理由，
所有下游行为与本条冲突时以本条为准（见设计文档 §0）。

主产物是**项目目录** `<project_root>/knowledge-base/`（检索端读的就是这里），
**不是** Obsidian。Obsidian 只是可选的人读副本。

---

## 定位与历史

distill 是一个**手动、按需**触发的沉淀器：把一个完成（或进行中）的 spec +
**当前 agent 上下文**，提炼成若干**原子知识点**（一需求扇出 N 份独立文档），
落到该 spec 所属项目的 `knowledge-base/`，并维护一份轻量索引 `MEMORY.md`。

**md-only** —— 无 yml、无 `codemap knowledge write`、无 `.ai-memory`、无任何
静默注入。历史沿革（仍然成立的事实）：

- v1-v3 的 distill 曾是「记忆 ingest 管线」，写 dual yml + md 到
  `<project_root>/.ai-memory/knowledge/` 供 `codemap recall` 在后续 spec 自动
  注入。Round 1/2 基线实验证明 recall 往返**并不净省 token**，4.0.0 整体拔除。
- yml / `codemap knowledge write` 路径在 5.0.1 移除（其唯一消费者 `codemap
  recall` 早在 4.0.0 已删，yml 无物可喂）。
- 当前形态（本次重写）：从「Obsidian-primary 5 类组织器」改为「项目
  `knowledge-base/` primary 的原子双轨（case + navigation）定位沉淀器 + 可选
  Obsidian 副本」。要 v3 的自动注入行为，checkout
  `backup/specode-v3.4.0-task-swarm-v0.9.2`。

---

## Trigger

```
/specode:distill <slug> [--target-dir <abs-path>]
```

| Arg | Default | Meaning |
|---|---|---|
| `<slug>` | (required) | spec slug under `<specsRoot>/` |
| `--target-dir` | (none) | **可选** Obsidian 副本目录（绝对路径；直写不拼接）。不给则 Step 5 用 `AskUserQuestion` 询问 |

主产物**固定**落 `<project_root>/knowledge-base/`，不可由参数改写。`project_root`
由 `resolve_root.py read-project-root --spec <specsRoot>/<slug>` 读取（来自该
spec `requirements.md` frontmatter 的 `project_root`），**不从 cwd 反推**。

**Manual only**：没有 auto-trigger。specode 主流程验收收尾后只**提示**入口
（「是否进入 distill 沉淀本次经验？」），不强制、不自动跑。用户想更新本项目的
定位库时才运行本命令。

---

## Inputs

| Source | What it provides |
|---|---|
| `<specsRoot>/<slug>/` | spec dir（**只读**）：`requirements.md` / `design.md` / `implementation-log.md` 等结构化事实 |
| `<specsRoot>/<slug>/requirements.md` YAML frontmatter | `project_root`（经 `read-project-root` 读出，用于定位主产物落盘目录） |
| **当前 agent 上下文** | 超出 spec 本身的**人类导航经验**：前后端调用链、页面按钮→哪个文件、什么配置映射到后端入口等，由模型从本轮上下文提炼并落地（navigation 型知识点的主来源） |

---

## Output structure

```
<project_root>/knowledge-base/         # 主产物（不提交项目仓库）
├── MEMORY.md                          # knowledge.py memory-rebuild 由各文档 frontmatter 生成
├── cases/<topic-kebab>.md             # 一个 case 型原子点一文件
└── navigation/<topic-kebab>.md        # 一个 navigation 型原子点一文件

<obsidian-target-dir>/                 # 可选副本：cp 文档过去 + 在该目录再跑一次 memory-rebuild
├── MEMORY.md
├── cases/...
└── navigation/...
```

- 文件按**主题** kebab 命名，**不按 slug**；`slug` 降级为文档 frontmatter 的
  `来源` 溯源字段。每个文档的 frontmatter / 正文结构以 `references/doc-template.md`
  为准（两类模板：`case` / `navigation`，frontmatter 键名固定）。
- `MEMORY.md` **不手改** —— 永远由 `knowledge.py memory-rebuild` 从各文档
  frontmatter 全量重建（frontmatter 是单一事实源）。

---

## Flow（5 步）

> 所有 `resolve_root.py` / `knowledge.py` 调用**必须**走 `run.sh` 包装器，并用
> 下面这段自包含 resolver 前缀解析 `$R`（skill 驱动的 Bash 调用里
> `$CLAUDE_PLUGIN_ROOT` 不一定有值，必须 `find` 兜底）：
>
> ```bash
> R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/specode/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
> ```

### Step 1 — 解析 slug + project_root，建目录，落 .gitignore

1. 先用 `resolve_root.py get-root` 取 `<specsRoot>`，确认
   `<specsRoot>/<slug>/requirements.md` 存在（否则报错退出）。
2. 读 `project_root`：
   ```bash
   sh "$R/scripts/run.sh" "$R/scripts/resolve_root.py" read-project-root --spec <specsRoot>/<slug>
   ```
   退出 0 → stdout 即 `project_root`；非 0（缺 frontmatter / 路径非法）→ 报错并
   提示该 spec 需先补 `project_root` 字段。
3. `mkdir -p <project_root>/knowledge-base/cases <project_root>/knowledge-base/navigation`
4. 确保 `knowledge-base/` 进项目 `.gitignore`（不提交仓库）：
   ```bash
   sh "$R/scripts/run.sh" "$R/scripts/knowledge.py" ensure-gitignore --project-root <project_root>
   ```

### Step 2 — 读全 spec + 回顾 agent 上下文（NO recall）

`Read` `<specsRoot>/<slug>/` 下每个 `.md`（requirements / design /
implementation-log 等），并回顾本轮 agent 上下文里反复用到的「找文件 / 调用链 /
配置映射」导航经验，留作 Step 3。

> **NO recall**：**不**读任何旧 KB（`knowledge-base/` / `MEMORY.md`）当事实
> 输入。distill 只**产出**指针，从不把历史 KB 当真相消费。不调用任何
> `codemap recall`，不读 `.ai-memory/`。

### Step 3 — `AskUserQuestion` 提案原子拆分（不可跳过）

按 `references/breakdown-heuristics.md` 把 spec + 上下文拆成若干**原子知识点**，
每点一文档，归入两类之一：

- `case` —— 本需求「改了什么 + 在哪些前后端文件 + 调用链 + 踩坑」（每个独立改动
  一个点，不要整需求塞一个文档）。
- `navigation` —— 超出本需求的**项目级导航经验**（页面按钮→文件、配置→后端入口、
  某类页面的定位套路），换个需求也能复用。

每个候选给 `标题 / 类型 / 来源(slug) / tags / 描述`；`tags` 取自**页面名 /
字段名 / 功能域**三类具体名词（不引入受控词表）。`AskUserQuestion` 让用户
confirm / add / drop / rename / recategorize，锁定后进 Step 4。

### Step 4 — 写 case/navigation 文档 + 重建 MEMORY

逐个把确认后的知识点按 `references/doc-template.md` 写入
`<project_root>/knowledge-base/{cases,navigation}/<topic-kebab>.md`（host agent
直接 author markdown，无外部 writer CLI）。

- 已存在同名文件 → `Read` 后问用户 `overwrite / skip / merge`。
- **navigation 跨 spec 去重合并**：由模型按 `tags` + `标题` 判定是否同一导航
  点——是则 merge/更新已有文档，否则新建；不重复造。

全部写完后，重建索引（由 frontmatter 全量重建，请勿手改 MEMORY.md）：
```bash
sh "$R/scripts/run.sh" "$R/scripts/knowledge.py" memory-rebuild --kb <project_root>/knowledge-base
```

### Step 5 — 双轨落盘（可选 Obsidian 副本）

`AskUserQuestion`「复制一份到 Obsidian 库？」：

- **不需要** → 结束。
- **需要** → 让用户**输入绝对路径**（明确提示：这是直接写入的目录，distill
  **不做任何拼接**）。若路径在 `/Volumes/` 下，先校验挂载
  （`ls "/Volumes/<name>"` 成功，否则拒绝并提示）。然后：
  ```bash
  cp -R <project_root>/knowledge-base/cases  <obsidian-target-dir>/
  cp -R <project_root>/knowledge-base/navigation <obsidian-target-dir>/
  sh "$R/scripts/run.sh" "$R/scripts/knowledge.py" memory-rebuild --kb <obsidian-target-dir>
  ```
  Obsidian 侧不在副本目录重新生成内容，只 `cp` + 重建该目录自己的 MEMORY。

> 双轨逻辑只属于 distill 自身：不影响主流程，也不影响检索端——检索端永远只读
> 项目目录的 `knowledge-base/`，绝不读 Obsidian 副本。

---

## Red lines

| Red line | Note |
|---|---|
| 主写域 = `<project_root>/knowledge-base/` | distill 的主产物固定落项目目录的 `cases/` + `navigation/` + `MEMORY.md` |
| Spec 目录只读 | 绝不修改 `<specsRoot>/<slug>/` 下任何文件 |
| `project_root` 单一来源 | 经 `resolve_root.py read-project-root --spec ...` 读取，**不从 cwd 反推** |
| Obsidian 是可选副本，直写不拼接 | `--target-dir` / 用户输入的绝对路径直接作为写入目录，distill 不做任何路径拼接 |
| `/Volumes/` 挂载校验 | 副本目录在 `/Volumes/` 下时先验挂载，未挂载则拒绝 |
| `knowledge-base/` 不提交仓库 | 本地私有定位资产；落盘时 `ensure-gitignore` 保证 `.gitignore` 含 `knowledge-base/` |
| Md-only | 只产 markdown —— 无 yml、无 `codemap knowledge write`、无 `.ai-memory` |
| NO recall / 无注入 | distill 不读旧 KB 当事实、不调 `codemap recall`；产物不喂任何后续 spec 的 `requirements.md`、不喂 task-swarm |
| MEMORY 不手改 | 永远由 `knowledge.py memory-rebuild` 从各文档 frontmatter 全量重建 |
| Read-before-overwrite | 目标 md 已存在 → `Read` 后问用户 overwrite / skip / merge |

---

## References

- `references/breakdown-heuristics.md` —— 原子知识点提炼 → case / navigation 两类映射。
- `references/doc-template.md` —— case / navigation 两类文档的 frontmatter + 正文模板。
